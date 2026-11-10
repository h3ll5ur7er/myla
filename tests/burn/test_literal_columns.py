"""Burn test: checking a list or map literal takes time linear in its elements
(MYLA-401's quadratic join, MYLA-417).

The checker keeps a literal column's open elements (those whose type had a
hole, `None` before the `Some` that fixes `T`) and its literals (which a later
element's type is given to, L2) in lists of its own, added to in place. They
used to be fields of the column, a value copied at every element: 64,000
`None`s and then a `Some(1)` took 40 seconds. Four times the elements must take
about four times as long, not sixteen."""
import os
import subprocess
import tempfile
import time
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, STDLIB_ROOT
from tests.burn._tools import selfhost_tool


def _program(kind: str, n: int) -> str:
    if kind == "nones":
        elems = "None, " * n + "Some(1)"
    elif kind == "literals":
        elems = "1, " * n + "3u8"
    else:
        elems = ", ".join(f"{i}: None" for i in range(n)) + ", 1u64: Some(1)"
    return f"fun main() {{\n    let a = [{elems}]\n    print(a.len())\n}}\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class LiteralColumns(unittest.TestCase):
    def _seconds(self, tmp: str, kind: str, n: int) -> float:
        path = os.path.join(tmp, f"{kind}_{n}.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_program(kind, n))
        start = time.perf_counter()
        proc = subprocess.run([selfhost_tool("main"), "check", path, "--stdlib", STDLIB_ROOT],
                              capture_output=True, text=True, timeout=300)
        took = time.perf_counter() - start
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return took

    def test_checking_scales_linearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ("nones", "literals", "map keys"):
                with self.subTest(kind=kind):
                    a = min(self._seconds(tmp, kind, 4000) for _ in range(3))
                    b = min(self._seconds(tmp, kind, 16000) for _ in range(3))
                    # eight times the time, not sixteen, plus slack for a busy machine
                    self.assertLess(b, 8 * a + 0.1, f"{kind}: 4,000 elements took {a:.3f} s, 16,000 {b:.3f} s")


if __name__ == "__main__":
    unittest.main()
