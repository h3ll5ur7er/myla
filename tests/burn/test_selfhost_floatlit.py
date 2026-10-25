"""The self-hosted compiler's float literal conversion (selfhost/floatlit.my,
MYLA-29) against Python: the correctly rounded double of each literal, and that
double rounded to float32, must be bit-identical to what the Python toolchain
uses (`float(text)`, then `struct` single-precision rounding)."""
import os
import random
import struct
import subprocess
import tempfile
import unittest

from myla.compiler import build
from myla.loader import default_stdlib_root, link
from myla.types import check

from ._native import CAN_BUILD_NATIVE, SKIP_REASON

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

TRICKY = [
    "0.0", "00.0", "0.5", "0.1", "0.2", "0.3", "1.0", "2f32", "2f64", "1_000.5", "1_0e1_0",
    "3.141592653589793", "2.718281828459045", "1e23", "8.98846567431158e307",
    "9007199254740992", "9007199254740993", "9007199254740995", "9007199254740997",
    "1.7976931348623157e308", "1.7976931348623158e308", "1.7976931348623159e308",
    "5e-324", "2.4703282292062327e-324", "2.4703282292062328e-324",
    "4.9406564584124654e-324", "2.2250738585072011e-308", "2.2250738585072014e-308",
    "1e-400", "1e400", "123456789012345678901234567890e-10",
    "0.000000000000000000000000000000000000000000000001",
    "3.4028234663852886e38", "3.4028235e38", "3.4028236e38", "1.401298464324817e-45",
    "7.006492321624085e-46", "7.006492321624086e-46", "1.1754943508222875e-38",
    "16777217.0", "16777219.0", "0.1f32", "1e-7f32", "6.103515625e-05",
]


def _random_literals(n: int) -> list[str]:
    rng = random.Random(29)
    out = []
    for _ in range(n):
        bits = rng.getrandbits(63) & ~(0x7FF << 52) | (rng.randrange(0, 2047) << 52)
        x = struct.unpack("<d", struct.pack("<Q", bits))[0]
        out.append(repr(x))                       # shortest round-trip form
        digits = "".join(rng.choice("0123456789") for _ in range(rng.randint(1, 40)))
        out.append(f"{digits[:1]}.{digits[1:] or '0'}e{rng.randint(-340, 320)}")
    return out


def _python_bits(lexeme: str) -> tuple[int, int]:
    text = lexeme.replace("_", "").split("f")[0]
    x = float(text)
    f64 = struct.unpack("<Q", struct.pack("<d", x))[0]
    try:
        f32 = struct.unpack("<Q", struct.pack("<d", struct.unpack("f", struct.pack("f", x))[0]))[0]
    except OverflowError:                         # beyond float32: infinity
        f32 = 0x7FF0000000000000
    return f64, f32


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestFloatLiteralBits(unittest.TestCase):
    def test_matches_python_bit_for_bit(self):
        literals = TRICKY + _random_literals(400)
        with tempfile.TemporaryDirectory() as tmp:
            tool = os.path.join(tmp, "floatlit")
            checker = check(link(os.path.join(_REPO, "selfhost", "floatlit_main.my"),
                                 stdlib_root=default_stdlib_root()))
            build(checker, tool)
            out = subprocess.run([tool, *literals], capture_output=True, text=True,
                                 check=True).stdout.split("\n")
        for lexeme, line in zip(literals, out):
            with self.subTest(literal=lexeme):
                got = tuple(int(x) for x in line.split())
                self.assertEqual(got, _python_bits(lexeme))
        self.assertEqual(len(out) - 1, len(literals))


if __name__ == "__main__":
    unittest.main()
