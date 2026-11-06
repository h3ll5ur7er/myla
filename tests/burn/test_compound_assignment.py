"""Burn test: compound assignment (D104 (2), MYLA-223).

`+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`, `<<=` and `>>=` mean
`x = x op y`, the place evaluated once (an index with a side effect runs
once), the operator's trait applying to a struct, `>>=` composing functions.
The self-hosted interpreter and native code agree; the target must be a
`var` place and the operator defined for its type."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """struct V {
    x: int,
    y: int,
}

impl Add for V {
    fun add(self, other: V) -> V {
        return V { x: self.x + other.x, y: self.y + other.y }
    }
}

struct Cell {
    n: int,
    items: [int],
}

fun pick(k: int) -> int {
    print(f"pick {k}")
    return k
}

fun inc(x: int) -> int {
    return x + 1
}

fun dbl(x: int) -> int {
    return x * 2
}

fun main() {
    var a = 10
    a += 5
    a -= 3
    a *= 4
    a /= 6
    a %= 5
    print(a)
    var b = 12
    b &= 10
    b |= 1
    b ^= 3
    b <<= 2
    b >>= 1
    print(b)
    var f = 1.5
    f *= 2.0
    print(f)
    var s = "ab"
    s += "cd"
    print(s)
    var xs = [1, 2, 3]
    xs[1] += 40
    xs[pick(2)] *= 10
    print(f"{xs[0]} {xs[1]} {xs[2]}")
    var cells = [Cell { n: 1, items: [5, 6] }, Cell { n: 2, items: [7] }]
    cells[pick(1)].n += 100
    cells[pick(0)].items[pick(1)] -= 6
    print(f"{cells[1].n} {cells[0].items[1]}")
    var m = ["k": 1]
    m["k"] += 9
    print(m["k"])
    var v = V { x: 1, y: 2 }
    v += V { x: 10, y: 20 }
    print(f"{v.x} {v.y}")
    var g: (int) -> int = inc
    g >>= dbl
    print(g(3))
    var big: int64 = 1
    big <<= 40
    print(big)
    var ys = [1, 2, 3, 4]
    ys[^1] += 5
    ys[^pick(3)] *= 2
    print(f"{ys[0]} {ys[1]} {ys[3]}")
}
"""

_WANT = ("3\n20\n3\nabcd\npick 2\n1 42 30\npick 1\npick 0\npick 1\n102 0\n10\n11 22\n8\n1099511627776\npick 3\n1 4 9\n")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class CompoundAssignment(unittest.TestCase):
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
        path = self.write("compound.my", _PROGRAM)
        proc = subprocess.run([self.myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))
        exe = os.path.join(self.tmp.name, "compound")
        built = subprocess.run([self.myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], capture_output=True,
                               text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        proc = subprocess.run([exe], capture_output=True, text=True)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))

    def test_errors(self):
        cases = {
            "let_target": ("fun main() {\n    let x = 1\n    x += 1\n}\n", "cannot assign to an immutable binding"),
            "no_operator": ("fun main() {\n    var s = \"a\"\n    s -= \"b\"\n}\n", "type error"),
            "not_a_place": ("fun f() -> int {\n    return 1\n}\nfun main() {\n    f() += 1\n}\n",
                            "invalid assignment target"),
            "mismatch": ("fun main() {\n    var x = 1\n    x += \"a\"\n}\n", "type error"),
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
