"""Burn test: let-else (D137, MYLA-256).

`let P = e else { … }` binds the pattern's names for the rest of the block
when `e` matches `P`; otherwise the `else` block runs, and it must leave the
block (`return`, `become`, `break`, `continue`, or a call that never returns:
`panic`, `unreachable`, `exit`). It is sugar over `match`, so the bindings'
ownership and drops follow the match's rules. The self-hosted interpreter and
native code agree."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_argv, target_flags
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """enum Shape {
    Circle(int),
    Rect(int, int),
}

fun area(s: Option<Shape>) -> Result<int, str> {
    let Some(shape) = s else {
        return Err("no shape")
    }
    let Shape.Rect(w, h) = shape else {
        return Err("not a rectangle")
    }
    return Ok(w * h)
}

fun shown(r: Result<int, str>) -> str {
    return match r { Ok(v) => f"ok {v}", Err(e) => f"err {e}" }
}

fun parse_digit(c: str) -> Option<int> {
    if c == "1" { return Some(1) }
    if c == "2" { return Some(2) }
    return None
}

fun sum_digits(cs: [str]) -> int {
    var total = 0
    for c in cs {
        let Some(d) = parse_digit(c) else {
            continue
        }
        total += d
    }
    return total
}

fun first_word(words: [str]) -> str {
    var i = 0
    var found = ""
    while true {
        let Some(w) = at(words, i) else {
            break
        }
        if w.len() > 0 {
            found = w
            break
        }
        i += 1
    }
    return found
}

fun at(xs: [str], i: int) -> Option<str> {
    if i < xs.len() { return Some(xs[i]) }
    return None
}

fun doubled(o: Option<int>, on: bool) -> int {
    let v = if on {
        let Some(x) = o else {
            return -1
        }
        x * 2
    } else {
        0
    }
    return v + 1
}

fun must(o: Option<str>) -> str {
    let Some(s) = o else {
        panic("missing")
    }
    return s
}

fun main() {
    print(shown(area(Some(Shape.Rect(3, 4)))))
    print(shown(area(Some(Shape.Circle(2)))))
    print(shown(area(None)))
    print(sum_digits(["1", "x", "2", "2"]))
    print(first_word(["", "", "hi", "yo"]))
    print(first_word([""]))
    print(doubled(Some(5), true))
    print(doubled(None, true))
    print(doubled(None, false))
    print(must(Some("here")))
    let names = ["ada", "bo"]
    let Some(n) = at(names, 1) else {
        return
    }
    print(n)
    print(must(None))
}
"""

_WANT = "ok 12\nerr not a rectangle\nerr no shape\n5\nhi\n\n11\n-1\n1\nhere\nbo\n"
_PANIC = "runtime error: missing\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class LetElse(unittest.TestCase):
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
        path = self.write("letelse.my", _PROGRAM)
        proc = subprocess.run([self.myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual((proc.stdout, proc.stderr.startswith(_PANIC), proc.returncode), (_WANT, True, 1), proc.stderr)
        exe = os.path.join(self.tmp.name, "letelse")
        built = subprocess.run([self.myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT, *target_flags()], capture_output=True,
                               text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        proc = subprocess.run(run_argv(exe, exe)[0], capture_output=True, text=True, timeout=60)
        self.assertEqual((proc.stdout, proc.stderr.startswith(_PANIC), proc.returncode), (_WANT, True, 1), proc.stderr)

    def test_exit_leaves_the_block(self):
        # `exit` never returns, so it leaves a let-else's `else` and ends a
        # function that returns a value, as the Statements page says
        src = ("from std.process import exit\nimport std.process as process\n\n"
               "fun f(o: Option<int>) -> int {\n    let Some(v) = o else {\n        exit(3)\n    }\n    return v\n}\n\n"
               "fun g(n: int) -> int {\n    if n > 0 {\n        return n\n    }\n    process.exit(2)\n}\n\n"
               "fun main() {\n    print(f(Some(1)))\n    print(g(0))\n}\n")
        path = self.write("exits.my", src)
        proc = subprocess.run([self.myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("1\n", "", 2))

    def test_errors(self):
        cases = {
            "falls_through": ("fun main() {\n    let o = Some(1)\n    let Some(v) = o else {\n        print(0)\n    }\n    print(v)\n}\n",
                              "type error: the 'else' of a let-else must leave the block"),
            "always_matches": ("enum One {\n    Only(int),\n}\n\nfun main() {\n    let Only(v) = One.Only(3) else {\n        return\n    }\n    print(v)\n}\n",
                               "type error: the pattern of this let-else always matches: use 'let' instead"),
            "mismatch": ("fun main() {\n    let Some(v) = 3 else {\n        return\n    }\n    print(v)\n}\n", "type error"),
            "no_else": ("fun main() {\n    let o = Some(1)\n    let Some(v) = o\n    print(v)\n}\n",
                        "parse error: expected 'else' after a let-else's value: a pattern that can fail to match needs one"),
            "scoped": ("fun f(o: Option<int>) {\n    if true {\n        let Some(v) = o else {\n            return\n        }\n        print(v)\n    }\n    print(v)\n}\n\nfun main() {\n    f(Some(1))\n}\n",
                       "type error: unknown name 'v'"),
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
