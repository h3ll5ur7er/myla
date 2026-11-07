"""Burn test: builtin functions as methods (D103, MYLA-221).

`xs.push(v)` is `push(xs, v)`: `len` of lists, maps, strings and builders,
`push` and `pop` of lists, `contains`, `remove` and `keys` of maps, `chars`
of strings, `append`, `append_byte` and `build` of builders. A mutating one
needs a `var` place, as the function does; a local of the same name doesn't
hide it; a type's own method of that name wins. The self-hosted interpreter
and native code agree."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """struct Bag {
    items: [int],
    names: [str: int],
}

impl Bag {
    fun add(var self, x: int) {
        self.items.push(x)
        self.names[f"n{x}"] = x
    }
    fun count(self) -> int {
        return self.items.len() + self.names.len()
    }
}

struct Word {
    text: str,
}

impl Word {
    fun len(self) -> int {
        return 100 + self.text.len()
    }
}

fun main() {
    var xs = [1, 2]
    xs.push(3)
    print(xs.len())
    let last = xs.pop()
    print(last)
    var grid = [[1], [2, 3]]
    grid[0].push(9)
    print(grid[0].len())
    var m = ["a": 1, "b": 2]
    print(m.contains("a"))
    m.remove("a")
    print(m.len())
    print(m.keys().len())
    let s = "héllo"
    let chars = s.chars()
    print(chars.len())
    print(s.len())
    var sb = StringBuilder()
    sb.append("ab")
    sb.append("xyz", 1, 3)
    sb.append_byte(33)
    print(sb.len())
    print(sb.build())
    var bag = Bag { items: [], names: [:] }
    bag.add(4)
    bag.add(5)
    print(bag.count())
    print(Word { text: "hey" }.len())
}
"""

_WANT = "3\n3\n2\ntrue\n1\n1\n5\n6\n5\nabyz!\n4\n103\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class BuiltinMethods(unittest.TestCase):
    def setUp(self) -> None:
        self.myla = selfhost_tool("main")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name: str, src: str) -> str:
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        return path

    def test_in_the_interpreter_and_natively(self):
        path = self.write("methods.my", _PROGRAM)
        proc = subprocess.run([self.myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))
        exe = os.path.join(self.tmp.name, "methods")
        built = subprocess.run([self.myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], capture_output=True,
                               text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        proc = subprocess.run([exe], capture_output=True, text=True)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))

    def test_errors(self):
        cases = {
            "immutable": ("fun main() {\n    let xs = [1]\n    xs.push(2)\n}\n", "type error"),
            "wrong_type": ("fun main() {\n    let s = \"a\"\n    print(s.keys())\n}\n", "type 'str' has no method 'keys'"),
            "arity": ("fun main() {\n    var xs = [1]\n    xs.push()\n}\n", "push() takes 1 argument"),
            # what the function forms' argument errors were (MYLA-221): the
            # receiver isn't counted, and a type without the method lacks it
            "no_arguments": ("fun main() {\n    let c = \"a\".chars(1)\n}\n", "chars() takes no arguments"),
            "append_arity": ("fun main() {\n    var sb = StringBuilder()\n    sb.append()\n}\n",
                             "append() takes 1 or 3 arguments"),
            "push_onto_a_call": ("fun g() -> [int] {\n    return [1]\n}\n\nfun main() {\n    g().push(1)\n}\n",
                                 "invalid assignment target"),
            # a list's `contains` is std.list's since D164 (MYLA-323): a map's
            # builtin on a value that has none
            "contains_on_an_int": ("fun main() {\n    let b = 1.contains(1)\n}\n",
                                   "type 'int32' has no method 'contains'"),
            "remove_from_a_let": ("fun main() {\n    let m = [1: 2]\n    m.remove(1)\n}\n",
                                  "remove() needs a mutable map (declare it with 'var')"),
            "len_of_an_int": ("fun main() {\n    let n = 1.len()\n}\n", "type 'int32' has no method 'len'"),
        }
        for name, (src, want) in cases.items():
            with self.subTest(case=name):
                path = self.write(name + ".my", src)
                proc = subprocess.run([self.myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                                      text=True)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertIn(want, proc.stderr)

    def test_the_function_forms_are_gone(self):
        # MYLA-221, D103: a builtin that is a method is called as one; its
        # function form is an error naming the method
        cases = {
            "push": ("fun main() {\n    var xs = [1]\n    push(xs, 2)\n}\n",
                     "'push' is a method: call it as 'x.push(…)'"),
            "len": ("fun main() {\n    print(len([1]))\n}\n", "'len' is a method: call it as 'x.len()'"),
            "build": ("fun main() {\n    var sb = StringBuilder()\n    print(build(sb))\n}\n",
                      "'build' is a method: call it as 'x.build()'"),
        }
        for name, (src, want) in cases.items():
            with self.subTest(case=name):
                path = self.write(name + ".my", src)
                proc = subprocess.run([self.myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                                      text=True)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertIn("type error: " + want, proc.stderr)
                self.assertIn(f"{name}.my:", proc.stderr)

    def test_a_mutating_method_changes_an_actor_field(self):
        # D95: a field checked before an `await` and changed after it, by the
        # method form as by the function form, directly or in a synchronous
        # method of the actor (MYLA-171)
        actor = ("actor Pay {\n    n: int,\n}\nimpl Pay {\n    fun charge(var self) -> bool {\n"
                 "        self.n = self.n + 1\n        return true\n    }\n}\n"
                 "actor Inv {\n    sold: [str],\n}\nimpl Inv {\n    fun note(var self, who: str) {\n        {note}\n"
                 "    }\n    async fun record(var self, p: Pay, who: str) {\n        if self.sold.len() < 10 {\n"
                 "            let paid = await p.charge()\n            {change}\n        }\n    }\n}\n"
                 "fun main() {}\n")
        for name, note, change in [("direct", "print(who)", "self.sold.push(who)"),
                                   ("in_a_method", "self.sold.push(who)", "self.note(who)"),
                                   ("pop", "print(who)", "self.sold.pop()")]:
            with self.subTest(case=name):
                path = self.write(name + ".my", actor.replace("{note}", note).replace("{change}", change))
                proc = subprocess.run([self.myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                                      text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("'self.sold' was checked before an 'await' and is changed after it", proc.stderr)


if __name__ == "__main__":
    unittest.main()
