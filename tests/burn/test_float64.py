"""Burn test: `float` is `float64` (D102, MYLA-220).

The alias `float` and a float literal without a suffix are `float64`;
`float32` and the `f32` suffix keep their meaning. The self-hosted
interpreter and native code agree on each: the double's precision and range
for the default, the single's for `float32`."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """fun half(x: float) -> float {
    return x / 2.0
}

fun main() {
    let a = 0.1
    let b = 0.2
    print(a + b)
    let big: float = 1.0e40
    print(big > 1.0e39)
    let f: float64 = half(3.0)
    print(f)
    let s: float32 = 0.1
    print(s + 0.2f32)
    let t = 16777217.0f32
    print(t == 16777216.0f32)
    let u = 16777217.0
    print(u == 16777216.0)
    print(1.0 / 3.0)
}
"""

# floats print in their shortest round-trip form, a single's as a single
# (D155)
_WANT = ("0.30000000000000004\ntrue\n1.5\n0.3\ntrue\nfalse\n0.3333333333333333\n")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Float64(unittest.TestCase):
    def test_the_default_float_is_a_double(self):
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "floats.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_PROGRAM)
            proc = subprocess.run([myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))
            exe = os.path.join(tmp, "floats")
            subprocess.run([myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], check=True,
                           capture_output=True)
            proc = subprocess.run([exe], capture_output=True, text=True)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))


if __name__ == "__main__":
    unittest.main()
