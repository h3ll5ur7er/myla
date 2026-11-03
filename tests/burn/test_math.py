"""Burn test: std.math (MYLA-248).

Every function of std.math on a few hundred inputs, among them NaN, the
infinities, both zeros and the edges of each function's domain: the
interpreter and native code give bit-identical results (the functions are
written in Myla on two primitives), and each result lies within the units in
the last place std.math documents of what Python's `math` (the C library)
gives. A NaN must be a NaN; a zero must have the right sign."""
import math
import os
import random
import struct
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool


def _bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _float(b: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", b))[0]


def _ulps(a: float, b: float) -> int:
    """How many representable floats apart `a` and `b` are."""
    def ordered(x):
        i = struct.unpack("<q", struct.pack("<d", x))[0]
        return i if i >= 0 else -(i & 0x7FFFFFFFFFFFFFFF)
    return abs(ordered(a) - ordered(b))


_SPECIAL = [0.0, -0.0, float("inf"), float("-inf"), float("nan"), 1.0, -1.0, 0.5, -0.5, 2.0, 5e-324, 1.7976931348623157e308]

# name -> (Python's function, allowed units in the last place, inputs)
def _integral(f):
    """C's trunc, floor or ceil: an integer as a float, keeping the sign of a
    zero (Python's int would lose it), and inf and NaN as they are."""
    def g(x):
        if not math.isfinite(x):
            return x
        r = float(f(x))
        return math.copysign(r, x) if r == 0.0 else r
    return g


rng = random.Random(242)
_UNARY = {
    "sqrt": (math.sqrt, 0, [rng.uniform(0, 1e6) for _ in range(150)] + [rng.uniform(0, 1e-300) for _ in range(20)]),
    "abs": (abs, 0, [rng.uniform(-1e9, 1e9) for _ in range(50)]),
    "trunc": (_integral(math.trunc), 0,
              [rng.uniform(-1e6, 1e6) for _ in range(100)] + [rng.uniform(-3, 3) for _ in range(50)]),
    "floor": (_integral(math.floor), 0,
              [rng.uniform(-1e6, 1e6) for _ in range(100)] + [rng.uniform(-3, 3) for _ in range(50)]),
    "ceil": (_integral(math.ceil), 0,
             [rng.uniform(-1e6, 1e6) for _ in range(100)] + [rng.uniform(-3, 3) for _ in range(50)]),
    "exp": (math.exp, 1, [rng.uniform(-745, 709) for _ in range(150)] + [rng.uniform(-1, 1) for _ in range(100)]),
    "ln": (math.log, 1, [rng.uniform(0, 1e300) for _ in range(50)] + [rng.uniform(0.5, 2) for _ in range(150)]
           + [rng.uniform(0, 1e-305) for _ in range(20)]),
    "log2": (math.log2, 1, [rng.uniform(0, 1e300) for _ in range(50)] + [rng.uniform(0.5, 4) for _ in range(150)]
             + [2.0 ** k for k in range(-60, 60)]),
    "log10": (math.log10, 1, [rng.uniform(0, 1e300) for _ in range(50)] + [rng.uniform(0.1, 10) for _ in range(150)]
              + [10.0 ** k for k in range(-5, 23)]),
    # small, medium (three-part π/2) and large (Payne-Hanek) arguments
    "sin": (math.sin, 1, [rng.uniform(-10, 10) for _ in range(150)] + [rng.uniform(-1e5, 1e5) for _ in range(100)]
            + [rng.uniform(-1, 1) * 10 ** rng.uniform(6.3, 300) for _ in range(100)]),
    "cos": (math.cos, 1, [rng.uniform(-10, 10) for _ in range(150)] + [rng.uniform(-1e5, 1e5) for _ in range(100)]
            + [rng.uniform(-1, 1) * 10 ** rng.uniform(6.3, 300) for _ in range(100)]),
    "tan": (math.tan, 4, [rng.uniform(-10, 10) for _ in range(150)] + [rng.uniform(-1e5, 1e5) for _ in range(50)]
            + [rng.uniform(-1, 1) * 10 ** rng.uniform(6.3, 300) for _ in range(50)]),
    "atan": (math.atan, 1, [rng.uniform(-10, 10) for _ in range(150)] + [rng.uniform(-1e20, 1e20) for _ in range(50)]),
    "asin": (math.asin, 4, [rng.uniform(-1, 1) for _ in range(150)]),
    "acos": (math.acos, 4, [rng.uniform(-1, 1) for _ in range(150)]),
}
_BINARY = {
    "atan2": (math.atan2, 4, [(rng.uniform(-10, 10), rng.uniform(-10, 10)) for _ in range(200)]
              + [(y, x) for y in (0.0, -0.0, 1.0, -1.0, float("inf"), float("-inf"))
                 for x in (0.0, -0.0, 1.0, -1.0, float("inf"), float("-inf"))]),
    "pow": (math.pow, 4, [(rng.uniform(0, 100), rng.uniform(-10, 10)) for _ in range(150)]
            + [(rng.uniform(-10, 10), float(rng.randint(-20, 20))) for _ in range(100)]
            + [(2.0, 0.5), (0.0, 2.0), (0.0, -1.0), (-8.0, 1.0 / 3.0), (1.0, float("nan"))]),
    "hypot": (math.hypot, 1, [(rng.uniform(-1e3, 1e3), rng.uniform(-1e3, 1e3)) for _ in range(150)]
              + [(1e300, 1e300), (1e-300, 1e-300), (3.0, 4.0), (float("inf"), float("nan"))]),
}


def _program() -> tuple[str, list[tuple[str, tuple[float, ...]]]]:
    cases = []
    for name, (_, _, xs) in _UNARY.items():
        for x in xs + _SPECIAL:
            cases.append((name, (x,)))
    for name, (_, _, xys) in _BINARY.items():
        for xy in xys:
            cases.append((name, xy))
    lines = ["import std.math as m", "", "fun main() {"]
    for name, args in cases:
        call = ", ".join(f"m.from_bits({_bits(a)}u64)" for a in args)
        lines.append(f"    print(m.to_bits(m.{name}({call})))")
    lines.append("}")
    return "\n".join(lines) + "\n", cases


def _expected(name: str, args: tuple[float, ...]) -> float:
    fn = _UNARY[name][0] if name in _UNARY else _BINARY[name][0]
    if name in ("ln", "log2", "log10") and args[0] == 0.0:
        return float("-inf")                 # C's answer; Python raises
    if name == "pow" and args[0] == 0.0 and args[1] < 0.0:
        odd = args[1] == math.trunc(args[1]) and math.trunc(args[1]) % 2 == 1
        return math.copysign(float("inf"), args[0]) if odd else float("inf")
    try:
        return fn(*args)
    except ValueError:
        return float("nan")
    except OverflowError:
        return math.copysign(float("inf"), 1.0)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class StdMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source, cls.cases = _program()
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "math_cases.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(cls.source)
        myla = selfhost_tool("main")
        exe = os.path.join(cls.tmp.name, "math_cases")
        built = subprocess.run([myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
        if built.returncode != 0:
            raise AssertionError(built.stderr)
        cls.native = subprocess.run([exe], capture_output=True, text=True, check=True).stdout.split()
        cls.interpreted = subprocess.run([myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True,
                                         check=True).stdout.split()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_the_interpreter_and_native_code_agree_bit_for_bit(self):
        self.assertEqual(len(self.native), len(self.cases))
        self.assertEqual(self.interpreted, self.native)

    def test_each_result_is_within_its_documented_error(self):
        for (name, args), out in zip(self.cases, self.native):
            got = _float(int(out))
            want = _expected(name, args)
            allowed = _UNARY[name][1] if name in _UNARY else _BINARY[name][1]
            with self.subTest(function=name, args=args):
                if math.isnan(want):
                    self.assertTrue(math.isnan(got), f"{name}{args} = {got!r}, expected NaN")
                elif want == 0.0 or math.isinf(want):
                    self.assertEqual((got, math.copysign(1.0, got)), (want, math.copysign(1.0, want)))
                else:
                    self.assertLessEqual(_ulps(got, want), allowed, f"{name}{args} = {got!r}, C gives {want!r}")


if __name__ == "__main__":
    unittest.main()
