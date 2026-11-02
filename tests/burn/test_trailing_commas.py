"""Burn test: one trailing-comma rule (D104 (4), MYLA-225).

A comma may follow the last element of every comma-separated list: arguments
(of calls and attributes), parameters (of functions, methods and lambdas),
list, map and tuple literals, struct fields and literals, enum variants and
their payloads, generic arguments and parameters, tuple and function types,
patterns and import lists. A one-element tuple keeps its comma. The
self-hosted interpreter and native code run the program alike."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """from std.io import println, eprintln,

struct Box<T,> {
    v: T,
}

struct P {
    x: int,
    y: int,
}

enum Shape {
    Dot,
    Line(int, int,),
}

impl P {
    fun sum(self, k: int,) -> int {
        return self.x + self.y + k
    }
}

#test(1, 2,)[3]
fun add(a: int, b: int,) -> int {
    return a + b
}

fun first<T, U,>(t: (T, U,),) -> T {
    return t.0
}

fun main() {
    println(f"{add(1, 2,)}")
    let f = (a: int, b: int,) => a * b
    print(f(3, 4,))
    let g: (int, int,) -> int = f
    print(g(2, 5))
    let b: Box<int,> = Box { v: 7, }
    print(b.v)
    let p = P { x: 1, y: 2, }
    print(p.sum(10,))
    print(first((5, "five",),))
    let one = (9,)
    print(one.0)
    let xs = [1, 2, 3,]
    let m = ["a": 1, "b": 2,]
    print(len(xs) + len(m))
    let (u, w,) = (4, 6,)
    print(u + w)
    match Shape.Line(3, 8,) {
        Shape.Line(s, e,) => print(e - s),
        Shape.Dot => print(0),
    }
    match (p) {
        P { x, y, } => print(x * y),
    }
}
"""

_WANT = "3\n12\n10\n7\n13\n5\n9\n5\n10\n5\n2\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TrailingCommas(unittest.TestCase):
    def test_every_list_takes_a_trailing_comma(self):
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "commas.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_PROGRAM)
            proc = subprocess.run([myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))
            exe = os.path.join(tmp, "commas")
            built = subprocess.run([myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], capture_output=True,
                                   text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            proc = subprocess.run([exe], capture_output=True, text=True)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))
            tested = subprocess.run([myla, "test", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_a_lone_comma_is_still_an_error(self):
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            for name, src in [("call", "fun f() {}\nfun main() {\n    f(,)\n}\n"),
                              ("params", "fun f(,) {}\nfun main() {}\n"),
                              ("double", "fun f(a: int) {}\nfun main() {\n    f(1,,)\n}\n")]:
                with self.subTest(case=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(src)
                    proc = subprocess.run([myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                                          text=True)
                    self.assertEqual(proc.returncode, 1, proc.stderr)
                    self.assertIn("parse error", proc.stderr)


if __name__ == "__main__":
    unittest.main()
