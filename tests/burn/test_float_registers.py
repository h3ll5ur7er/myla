"""Burn test: float values in xmm registers (MYLA-249).

A float temporary whose interval holds no call lives in one of %xmm2..%xmm15,
and float arithmetic, comparisons and `sqrt` work on it there, instead of
moving every operand from a general-purpose register into %xmm0/%xmm1 and the
result back. The mandelbrot loop shows it in its code; programs of floats
(float32 rounding, NaN, signed zeros, casts, sqrt, values across calls and
loops) print the same natively as in the interpreter."""
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_MANDEL = """fun inside(cr: float64, ci: float64) -> bool {
    var zr = 0.0
    var zi = 0.0
    var i = 0
    while i < 50 {
        let tr = zr * zr - zi * zi + cr
        zi = 2.0 * zr * zi + ci
        zr = tr
        if zr * zr + zi * zi > 4.0 {
            return false
        }
        i += 1
    }
    return true
}

fun main() {
    print(inside(0.1, 0.2))
}
"""

_PROGRAM = """from std.math import sqrt, to_bits

fun dist(x: float64, y: float64) -> float64 {
    return sqrt(x * x + y * y)
}

fun mixed(a: float64, n: int) -> float64 {
    var s = a
    for i in 0..n {
        s = s * 1.5 - (i as float64) / 3.0
        if s > 1000.0 {
            s = s / 7.0
        }
    }
    return s
}

fun narrow(a: float32, b: float32) -> float32 {
    let c = a * b + a / b
    return c - b
}

fun main() {
    print(dist(3.0, 4.0))
    print(mixed(0.7, 40))
    print(narrow(1.1f32, 2.3f32))
    let z = 0.0
    let nz = -z
    print(to_bits(nz * 2.0))
    let nan = z / z
    print(nan < 1.0)
    print(nan != nan)
    print(nan == nan)
    print(1.0 / nz < 0.0)
    // float comparisons that branch, NaN on either side
    var hits = 0
    for v in [0.5, 1.0, 1.5, nan, -0.0, 0.0] {
        if v > 1.0 { hits += 1 }
        if v >= 1.0 { hits += 10 }
        if v < 1.0 { hits += 100 }
        if v <= 1.0 { hits += 1000 }
        if 1.0 < v { hits += 10000 }
        if v <= nan { hits += 100000 }
    }
    print(hits)
    var total = 0.0
    for k in 1..2000 {
        total += dist(k as float64, 1.0 / (k as float64))
    }
    print(total)
    let big = 1.0e300 * 1.0e10
    print(big > 1.0e308)
    print((mixed(2.5, 7) * 100.0) as int64)
}
"""


def _function(asm: str, name: str) -> str:
    m = re.search(rf"^myla_{name}:\n(.*?)(?=^myla_\w+:|\Z)", asm, re.S | re.M)
    if not m:
        raise AssertionError(f"no function {name}")
    return m.group(1)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class FloatRegisters(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name: str, text: str) -> str:
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_the_loop_computes_in_xmm_registers(self):
        path = self.write("mandel.my", _MANDEL)
        asm = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT], capture_output=True, text=True,
                             check=True).stdout
        body = _function(asm, "inside")
        # operands moved between general-purpose and xmm registers: only for
        # constants (and none per variable use)
        crossings = re.findall(r"movq %r\w+, %xmm[0-9]+", body)
        self.assertLessEqual(len(crossings), 6, "\n".join(crossings))
        homes = re.findall(r"(?:addsd|subsd|mulsd|divsd|ucomisd) %xmm([2-9]|1[0-5]),", body)
        self.assertGreaterEqual(len(homes), 4, body)

    def test_floats_print_the_same_natively_and_interpreted(self):
        path = self.write("floats.my", _PROGRAM)
        myla = selfhost_tool("main")
        ran = subprocess.run([myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        exe = os.path.join(self.tmp.name, "floats")
        built = subprocess.run([myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], capture_output=True,
                               text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        native = subprocess.run([exe], capture_output=True, text=True)
        self.assertEqual((native.stdout, native.returncode), (ran.stdout, 0))
        self.assertIn("5\n", ran.stdout)


if __name__ == "__main__":
    unittest.main()
