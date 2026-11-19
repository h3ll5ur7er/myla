"""Burn test: a float prints in its shortest round-trip form (D155,
MYLA-300).

`print`, `str` and an f-string hole without a spec give the fewest
significant digits that read back as the same value: a `float64`'s as a
float64, a `float32`'s as that float32 (a literal is read as a float64 and
rounded, so the check is the same). Plain digits from 1e-4 up to 1e16, the
digits and an exponent outside (`1.5e-7`, `1e300`). Every value below is
checked against Python's shortest repr, laid out by those rules, in the
interpreter and natively."""
import os
import random
import struct
import subprocess
import tempfile
import unittest

from tests.burn._native import (CAN_BUILD_NATIVE, SKIP_REASON, Program, native_build, run_source_both_now,
                                write_program)
from tests.burn.test_check_cost import COUNTER, instructions


def _f32(x: float) -> float:
    try:
        return struct.unpack("f", struct.pack("f", x))[0]
    except OverflowError:
        return float("inf")


def _digits(x: float, single: bool) -> tuple[str, int]:
    """The shortest digits of positive `x` that read back, and its exponent."""
    for n in range(1, 18):
        text = "%.*e" % (n - 1, x)
        back = float(text)
        if (_f32(back) if single else back) == x:
            mant, exp = text.split("e")
            return mant.replace(".", "").rstrip("0") or "0", int(exp)
    raise AssertionError(x)


def _shown(x: float, single: bool = False) -> str:
    if x != x:
        return "nan"
    if x in (float("inf"), float("-inf")):
        return "inf" if x > 0 else "-inf"
    sign = "-" if str(x).startswith("-") else ""
    x = abs(x)
    if x == 0:
        return sign + "0"
    d, e = _digits(x, single)
    if e < -4 or e >= 16:
        return sign + d[0] + ("." + d[1:] if len(d) > 1 else "") + "e" + str(e)
    if e >= len(d) - 1:
        return sign + d + "0" * (e - (len(d) - 1))
    if e >= 0:
        return sign + d[:e + 1] + "." + d[e + 1:]
    return sign + "0." + "0" * (-e - 1) + d


_DOUBLES = [0.1, 0.2, 0.3, 1.0, 100.0, 123456.789, 1 / 3, 2 / 3, 1e16, 9999999999999998.0, 1e15, 1e-4, 9.9e-5,
            1.5e-7, 5e-324, 2.2250738585072014e-308, 1.7976931348623157e308, 1e21, 1e300, 3.141592653589793,
            -2.5, -0.0, 0.30000000000000004, 123456789012345680000.0, 4.35, 0.0001, 12345678901234567.0]
_rng = random.Random(155)
_DOUBLES += [struct.unpack("d", struct.pack("Q", _rng.getrandbits(62) | (1 << 61) * _rng.getrandbits(1)))[0]
             for _ in range(120)]
_DOUBLES += [_rng.uniform(0, 1000) for _ in range(120)]
_DOUBLES = [x for x in _DOUBLES if x == x and abs(x) != float("inf")]
_SINGLES = [_f32(x) for x in (0.1, 0.2, 0.3, 1.0, 3.4028234663852886e38, 1.401298464324817e-45, 16777216.0, 1e-5,
                              3.14159, 123456.789, 1e10, 0.001)]
_SINGLES += [_f32(_rng.uniform(0, 100)) for _ in range(60)]


def _program() -> str:
    lines = ["fun main() {"]
    for x in _DOUBLES:
        lines.append(f"    print({repr(x)})")
    for x in _SINGLES:
        lines.append(f"    print({repr(x)}f32)")
    lines.append('    let a = 0.1 + 0.2')
    lines.append('    print(f"{a} {1.0e-7} {2.5e20}")')
    lines.append("}")
    return "\n".join(lines) + "\n"


def _want() -> str:
    out = [_shown(x) for x in _DOUBLES] + [_shown(x, True) for x in _SINGLES]
    out.append(f"{_shown(0.1 + 0.2)} {_shown(1e-7)} {_shown(2.5e20)}")
    return "\n".join(out) + "\n"


def _print_form(x: float) -> str:
    """`x` laid out as Myla prints it, with the digits of Python's repr (the
    fewest that read back, the nearest of them)."""
    r = repr(x)
    if r in ("nan", "inf", "-inf"):
        return r
    sign = "-" if r.startswith("-") else ""
    mant, _, exp = r.lstrip("-").partition("e")
    whole, _, frac = mant.partition(".")
    digits = whole + frac
    e = int(exp or 0) + len(whole) - 1 - (len(digits) - len(digits.lstrip("0")))
    digits = digits.strip("0")
    if not digits:
        return sign + "0"
    if e < -4 or e >= 16:
        return sign + digits[0] + ("." + digits[1:] if len(digits) > 1 else "") + "e" + str(e)
    if e >= len(digits) - 1:
        return sign + digits + "0" * (e - (len(digits) - 1))
    if e >= 0:
        return sign + digits[:e + 1] + "." + digits[e + 1:]
    return sign + "0." + "0" * (-e - 1) + digits


def _f64(bits: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", bits))[0]


# Floats of any exponent (MYLA-849): 200 of random bits, and powers of two
# with the floats either side of them, where the gap below is half the gap
# above (the nearest digits of a count may read back as the float below and
# the next ones up as this one: those are the shortest)
_rng849 = random.Random(849)
_RANDOM_BITS = [b for b in (_rng849.getrandbits(64) for _ in range(220)) if (b >> 52) & 2047 != 2047][:200]
# 200 such floats printed natively: 674,605,692 instructions when each
# candidate's digits were read back in big integers, 1,938,819 since
# (callgrind, 2026-11-18 over 3add216; the program without the floats
# 440,068): the bound has twice that headroom (MYLA-849)
PRINT_BOUND = 4_000_000
_EDGE_BITS = [c for e in range(0, 2047, 3) for c in ((e << 52) - 1, e << 52, (e << 52) + 1) if 0 < c < (2047 << 52)]


def _bits_program(bits: list[int], format_float: bool) -> str:
    """A program printing the float64 of each of `bits`, and its
    `num.format_float` after it with `format_float`."""
    rows = ",\n".join("        " + ", ".join(f"{b}u64" for b in bits[i:i + 4]) for i in range(0, len(bits), 4))
    shown = 'print(f"{x} {num.format_float(x)}")' if format_float else "print(x)"
    return ("import std.float as float\nimport std.num as num\n\nfun main() {\n    let bits: [uint64] = [\n" + rows +
            ",\n    ]\n    for b in bits {\n        let x = float.from_bits(b)\n        " + shown + "\n    }\n}\n")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class FloatPrint(unittest.TestCase):
    def test_the_layout(self):
        # the rules themselves, on values whose text is known
        self.assertEqual([_shown(x) for x in (0.1, 1.0, 1e16, 1.5e-7, 1e300, 0.30000000000000004, 1e-4, -0.0)],
                         ["0.1", "1", "1e16", "1.5e-7", "1e300", "0.30000000000000004", "0.0001", "-0"])
        self.assertEqual(_shown(_f32(0.1), True), "0.1")

    def test_shortest_round_trip_in_both_runners(self):
        self.assertEqual(run_source_both_now(_program()), (_want(), "", 0))

    def test_any_exponent_as_python_repr_in_both_runners(self):
        # `print` and std.num's `format_float` (in Python's layout) give
        # repr's digits, in the interpreter and natively (MYLA-849)
        bits = _RANDOM_BITS + _EDGE_BITS
        want = "".join(f"{_print_form(_f64(b))} {repr(_f64(b))}\n" for b in bits)
        self.assertEqual(run_source_both_now(_bits_program(bits, True)), (want, "", 0))

    @unittest.skipUnless(COUNTER, "no instruction counter (valgrind or perf) here")
    def test_random_floats_print_in_few_instructions(self):
        # 200 floats of random bits, natively (MYLA-849)
        with tempfile.TemporaryDirectory() as tmp:
            binary = os.path.join(tmp, "prog")
            native_build(Program(write_program(tmp, _bits_program(_RANDOM_BITS, False))), binary)
            out = subprocess.run([binary], capture_output=True, text=True, check=True).stdout
            self.assertEqual(out, "".join(_print_form(_f64(b)) + "\n" for b in _RANDOM_BITS))
            n = instructions([binary], tmp)
            self.assertLessEqual(n, PRINT_BOUND, f"printing 200 floats ran {n:,} instructions (by {COUNTER})")


if __name__ == "__main__":
    unittest.main()
