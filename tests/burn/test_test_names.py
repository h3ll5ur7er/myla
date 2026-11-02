"""Burn test: named `#test` cases (MYLA-239).

A line comment after a `#test(args)[expected]` attribute names the case:
`myla test` reports it after the case's number, `PASS  add #2 (sums
negatives)`, and on a failure before the detail. A case without one is
reported as before; a comment after another attribute names nothing."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """#test(1, 2)[3]
#test(-1, -2)[-3] // sums negatives
#test(2, 2)[5]    //   wrong on purpose
fun add(a: int, b: int) -> int {
    return a + b
}

#derive(Eq) // not a test
struct P {
    x: int,
}

impl P {
    #test(P { x: 2 }, 3)[5] // a method's case
    fun plus(self, k: int) -> int {
        return self.x + k
    }
}

fun main() {}
"""

_WANT = ("PASS  add #1\n"
         "PASS  add #2 (sums negatives)\n"
         "FAIL  add #3 (wrong on purpose): expected 5, got 4\n"
         "PASS  P.plus #1 (a method's case)\n")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestNames(unittest.TestCase):
    def test_a_comment_names_a_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "named.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_PROGRAM)
            proc = subprocess.run([selfhost_tool("main"), "test", path, "--stdlib", STDLIB_ROOT],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, _WANT + "\n3/4 passed.\n")


if __name__ == "__main__":
    unittest.main()
