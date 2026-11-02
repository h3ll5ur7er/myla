"""Burn test: `if let` and `while let` (D104 (5), MYLA-226).

`if let P = e { … } else { … }` runs its block with the pattern's bindings
when `e` matches `P`; `while let P = e { … }` loops while it does. Both are
sugar over `match`; the bindings are scoped to the block; an `if let` can be
a value, chain with `else if`, and stand in a `while let`'s body. A pattern
that always matches is an error. The self-hosted interpreter and native code
agree."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """enum Token {
    Num(int),
    Word(str),
    End,
}

fun first_even(xs: [int]) -> Option<int> {
    for x in xs {
        if x % 2 == 0 {
            return Some(x)
        }
    }
    return None
}

fun describe(t: Token) -> str {
    return if let Token.Num(n) = t {
        f"number {n}"
    } else if let Token.Word(w) = t {
        f"word {w}"
    } else {
        "end"
    }
}

fun main() {
    if let Some(e) = first_even([3, 5, 8, 9]) {
        print(e)
    }
    if let Some(e) = first_even([1, 3]) {
        print(e)
    } else {
        print("none")
    }
    print(describe(Token.Num(4)))
    print(describe(Token.Word("hi")))
    print(describe(Token.End))
    var stack = [1, 2, 3]
    var total = 0
    while let Some(top) = pop_opt(stack) {
        stack = shrink(stack)
        if top == 2 {
            continue
        }
        total += top
    }
    print(total)
    var queue = [Token.Num(1), Token.Word("x"), Token.Num(5), Token.End, Token.Num(9)]
    var i = 0
    var sum = 0
    while let Token.Num(n) = queue[i] {
        sum += n
        i += 1
    }
    print(sum)
    let fallback = if let Some(v) = first_even([7]) { v } else { -1 }
    print(fallback)
    let pair = (Some(3), 4)
    if let (Some(a), b) = pair {
        print(a + b)
    }
}

fun pop_opt(xs: [int]) -> Option<int> {
    if len(xs) == 0 {
        return None
    }
    return Some(xs[len(xs) - 1])
}

fun shrink(xs: [int]) -> [int] {
    var out = xs
    let gone = pop(out)
    return out
}
"""

_WANT = "8\nnone\nnumber 4\nword hi\nend\n4\n1\n-1\n7\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class IfLet(unittest.TestCase):
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
        path = self.write("iflet.my", _PROGRAM)
        proc = subprocess.run([self.myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))
        exe = os.path.join(self.tmp.name, "iflet")
        built = subprocess.run([self.myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], capture_output=True,
                               text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        proc = subprocess.run([exe], capture_output=True, text=True, timeout=60)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))

    def test_errors(self):
        cases = {
            "irrefutable": ("fun main() {\n    if let x = 5 {\n        print(x)\n    }\n}\n",
                            "type error: the pattern of this 'if let' always matches: use 'let' instead"),
            "irrefutable_while": ("fun main() {\n    while let (a, b) = (1, 2) {\n        print(a)\n    }\n}\n",
                                  "type error: the pattern of this 'while let' always matches: use 'while true' and 'let'"),
            "scoped": ("fun main() {\n    let o = Some(1)\n    if let Some(v) = o {\n        print(v)\n    }\n    print(v)\n}\n",
                       "type error: unknown name 'v'"),
            "mismatch": ("fun main() {\n    if let Some(v) = 3 {\n        print(v)\n    }\n}\n", "type error"),
            "no_equals": ("fun main() {\n    if let Some(v) {\n        print(v)\n    }\n}\n",
                          "parse error: expected '=' after the pattern of an 'if let'"),
        }
        for name, (src, want) in cases.items():
            with self.subTest(case=name):
                path = self.write(name + ".my", src)
                proc = subprocess.run([self.myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                                      text=True)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertIn(want, proc.stderr)


if __name__ == "__main__":
    unittest.main()
