"""Burn test: `if` as an expression (D104 (1), MYLA-222).

`let x = if c { a } else { b }`: each branch block ends in an expression,
its value; `else` is required; the branches' types must agree, as a
`match`'s arms do; `else if` chains. The self-hosted interpreter and native
code agree, and the errors say `if`, not `match`."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """fun sign(n: int) -> str {
    return if n < 0 {
        "negative"
    } else if n == 0 {
        "zero"
    } else {
        "positive"
    }
}

fun clamp(x: int, lo: int, hi: int) -> int {
    return if x < lo { lo } else { if x > hi { hi } else { x } }
}

struct P {
    x: int,
    y: int,
}

fun main() {
    print(sign(-4))
    print(sign(0))
    print(sign(9))
    print(clamp(15, 0, 10))
    let n = 7
    let parity = if n % 2 == 0 { "even" } else { "odd" }
    print(parity)
    let big = if n > 5 {
        let doubled = n * 2
        doubled + 1
    } else {
        0
    }
    print(big)
    print(if n > 0 { 1 } else { -1 } + 10)
    let p = if n > 3 { P { x: 1, y: 2 } } else { P { x: 0, y: 0 } }
    print(p.y)
    var total = 0
    for i in 0..5 {
        total += if i % 2 == 0 { i } else { 0 }
    }
    print(total)
    // the statement form is unchanged
    if n > 100 {
        print("never")
    }
}
"""

_WANT = "negative\nzero\npositive\n10\nodd\n15\n11\n2\n6\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class IfExpression(unittest.TestCase):
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
        path = self.write("ifexpr.my", _PROGRAM)
        proc = subprocess.run([self.myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))
        exe = os.path.join(self.tmp.name, "ifexpr")
        built = subprocess.run([self.myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], capture_output=True,
                               text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        proc = subprocess.run([exe], capture_output=True, text=True)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))

    def test_errors(self):
        cases = {
            "no_else": ("fun main() {\n    let x = if true { 1 }\n}\n",
                        "parse error: an 'if' used as a value needs an 'else'"),
            "types_differ": ("fun main() {\n    let x = if true { 1 } else { \"a\" }\n}\n",
                             "type error: the branches of an 'if' have incompatible types 'int32' and 'str'"),
            "no_value": ("fun main() {\n    let x = if true { let y = 1 } else { 2 }\n}\n",
                         "type error: this 'if' is used as a value, so every branch must produce one"),
            "not_bool": ("fun main() {\n    let x = if 1 { 1 } else { 2 }\n}\n", "type error"),
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
