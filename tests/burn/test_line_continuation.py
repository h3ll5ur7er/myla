"""Burn test: line continuation (D104 (3), MYLA-224).

A newline inside `( )` or `[ ]` (but not inside a `{ }` block within them)
and a newline after a binary operator that ends a line don't end the
statement; a line that starts with an operator still starts a new one, and
a line that ends in `>` (which also closes a generic type) still ends. The
self-hosted interpreter and native code agree."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """struct Box<T> {
    v: T,
}

typealias Num = Box<int>
fun inc(x: int) -> int {
    return x + 1
}

fun mul(x: int, k: int) -> int {
    return x * k
}

fun add3(
    a: int,
    b: int,
    c: int
) -> int {
    return a + b + c
}

fun apply(f: (int) -> int, x: int) -> int {
    return f(x)
}

fun main() {
    let x = 1 +
        2 *
        3
    print(x)
    let ok = x > 5 &&
        x < 10
    print(ok)
    let y = 5 |>
        inc |>
        mul(3)
    print(y)
    let z = (1
        + 2
        - 10)
    print(z)
    print(add3(
        1,
        2,
        3
    ))
    let xs = [10, 20, 30]
    print(xs[
        1
    ])
    let t = (1,
        "two")
    print(t.1)
    let w = apply((v: int) => {
        let u = v + 1
        return u * 2
    }, 3)
    print(w)
    print(match w {
        8 => "eight"
        _ => "other"
    })
    let n: Num = Box { v: 4 }
    print(n.v)
    var b = 10
    - 3
    print(b)
}
"""

_WANT = "7\ntrue\n18\n-7\n6\n20\ntwo\n8\neight\n4\n10\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class LineContinuation(unittest.TestCase):
    def test_continued_lines_in_the_interpreter_and_natively(self):
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cont.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_PROGRAM)
            proc = subprocess.run([myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))
            exe = os.path.join(tmp, "cont")
            built = subprocess.run([myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], capture_output=True,
                                   text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            proc = subprocess.run([exe], capture_output=True, text=True)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))

    def test_an_operator_at_the_end_of_the_file(self):
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "open.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("fun main() {\n    let x = 1 +\n}\n")
            proc = subprocess.run([myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("parse error: expected an expression, found '}'", proc.stderr)


if __name__ == "__main__":
    unittest.main()
