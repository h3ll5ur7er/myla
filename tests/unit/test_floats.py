"""Unit tests for floats (v0.5.2, D56): lexing, parsing, type checking, the
shared `format_float` renderer, and interpreter semantics."""
import io
import math
import struct
import unittest

from myla import ast
from myla.errors import LexError, TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.tokens import TokenKind
from myla.types import FloatType, check, format_float


def kinds(src: str) -> list[TokenKind]:
    return [t.kind for t in tokenize(src) if t.kind is not TokenKind.NEWLINE][:-1]


def first_float_token(src: str):
    for t in tokenize(src):
        if t.kind is TokenKind.FLOAT:
            return t
    raise AssertionError("no FLOAT token")


def run(src: str) -> str:
    out = io.StringIO()
    Interpreter(check(parse(tokenize(src))), out).run()
    return out.getvalue()


class TestFloatLexing(unittest.TestCase):
    def test_fractional_literal(self):
        t = first_float_token("3.14")
        self.assertEqual(t.value, 3.14)
        self.assertIsNone(t.suffix)

    def test_suffixes(self):
        self.assertEqual(first_float_token("6f32").value, 6.0)
        self.assertEqual(first_float_token("6f32").suffix, "f32")
        self.assertEqual(first_float_token("2.5f64").suffix, "f64")

    def test_exponent_forms(self):
        self.assertEqual(first_float_token("1.5e3").value, 1500.0)
        self.assertEqual(first_float_token("1e10").value, 1e10)
        self.assertEqual(first_float_token("3.14e-2f64").value, 3.14e-2)

    def test_underscores_in_float(self):
        self.assertEqual(first_float_token("1_000.5").value, 1000.5)

    def test_range_is_not_a_float(self):
        # `2..10` must stay INT DOTDOT INT, not consume a fractional part.
        self.assertEqual(
            kinds("2..10"),
            [TokenKind.INT, TokenKind.DOTDOT, TokenKind.INT],
        )

    def test_trailing_dot_then_ident_is_int(self):
        # `3.foo` is INT DOT IDENT (no fraction since the dot isn't followed by a digit)
        self.assertEqual(
            kinds("3.foo"),
            [TokenKind.INT, TokenKind.DOT, TokenKind.IDENT],
        )

    def test_invalid_float_suffix(self):
        with self.assertRaises(LexError):
            tokenize("1.5f16")

    def test_trailing_ident_after_float(self):
        with self.assertRaises(LexError):
            tokenize("1.5abc")


class TestFloatParsing(unittest.TestCase):
    def test_float_lit_node(self):
        prog = parse(tokenize("fun main() { let x = 3.5f64 }\n"))
        body = prog.decls[0].body.statements
        lit = body[0].init
        self.assertIsInstance(lit, ast.FloatLit)
        self.assertEqual(lit.value, 3.5)
        self.assertEqual(lit.suffix, "f64")


class TestFloatChecking(unittest.TestCase):
    def test_unsuffixed_defaults_to_float32(self):
        prog = parse(tokenize("fun main() { let x = 2.0 }\n"))
        check(prog)
        lit = prog.decls[0].body.statements[0].init
        self.assertEqual(lit.resolved_type, FloatType(32))

    def test_suffix_and_annotation(self):
        check(parse(tokenize("fun main() { let x: float64 = 1.5 }\n")))
        check(parse(tokenize("fun main() { let x = 1.5f64 }\n")))
        check(parse(tokenize("fun main() { let x: float = 1.5 }\n")))  # float == float32

    def test_no_int_float_mixing(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize("fun main() { let a = 1\n let b = 2.0\n print(a + b) }\n")))

    def test_no_float_width_mixing(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "fun main() { let a = 1.0f32\n let b = 2.0f64\n print(a + b) }\n")))

    def test_bitwise_on_float_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize("fun main() { print(1.5 & 2.0) }\n")))

    def test_casts_between_numeric(self):
        check(parse(tokenize("fun main() { print(5 as float64) }\n")))
        check(parse(tokenize("fun main() { print(3.9 as int32) }\n")))
        check(parse(tokenize("fun main() { print(1.5f32 as float64) }\n")))

    def test_float_not_a_map_key(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize("fun main() { let m: [float64: int] = [:] }\n")))


class TestFormatFloat(unittest.TestCase):
    F32 = FloatType(32)
    F64 = FloatType(64)

    def test_basic_values(self):
        self.assertEqual(format_float(2.0, self.F64), "2")
        self.assertEqual(format_float(3.5, self.F64), "3.5")
        self.assertEqual(format_float(-42.5, self.F64), "-42.5")
        self.assertEqual(format_float(0.0, self.F64), "0")
        self.assertEqual(format_float(-0.0, self.F64), "-0")
        self.assertEqual(format_float(123.456, self.F64), "123.456")

    def test_non_finite(self):
        self.assertEqual(format_float(math.inf, self.F64), "inf")
        self.assertEqual(format_float(-math.inf, self.F64), "-inf")
        self.assertEqual(format_float(math.nan, self.F64), "nan")

    def test_roundtrip_f64(self):
        import random
        random.seed(11)
        for _ in range(20000):
            v = random.uniform(-1e6, 1e6) * (10 ** random.randint(-9, 9))
            self.assertEqual(float(format_float(v, self.F64)), v)

    def test_roundtrip_f64_over_the_whole_range(self):
        import random
        random.seed(29)
        for _ in range(20000):
            v = struct.unpack("<d", struct.pack("<Q", random.getrandbits(63)))[0]
            if v != v or v == math.inf:
                continue
            self.assertEqual(float(format_float(v, self.F64)), v, repr(v))

    def test_largest_magnitudes_print_correctly_rounded_digits(self):
        # Dekker's split overflowed for operands above ~1.3e300 (the largest
        # doubles, and tiny ones scaled by 10^300..10^308), so the correction
        # term was dropped (the interpreter) or turned into garbage (native
        # code) (MYLA-29).
        for v in (1.7976931348623157e308, 3e300, 9.999999999999999e299, 1e-290,
                  1.2345678901234567e-288):
            expected = ("%.16e" % v).split("e")[0].replace(".", "").rstrip("0")
            got = format_float(v, self.F64).lstrip("0.").replace(".", "").rstrip("0")
            self.assertEqual(got, expected, repr(v))

    def test_roundtrip_f32(self):
        import random
        random.seed(13)
        for _ in range(20000):
            fv = struct.unpack("f", struct.pack("I", random.getrandbits(32)))[0]
            if fv != fv or fv in (math.inf, -math.inf):
                continue
            s = format_float(float(fv), self.F32)
            self.assertEqual(struct.unpack("f", struct.pack("f", float(s)))[0], fv)


class TestFloatInterpreter(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(run("fun main() { print(1.5 + 2.25) }\n"), "3.75\n")
        self.assertEqual(run("fun main() { print(7.0 / 2.0) }\n"), "3.5\n")
        self.assertEqual(run("fun main() { print(5.5 % 2.0) }\n"), "1.5\n")

    def test_precision_differs_by_type(self):
        self.assertEqual(run("fun main() { print(0.1f64 + 0.2f64) }\n"),
                         "0.30000000000000004\n")
        self.assertEqual(run("fun main() { print(0.1f32 + 0.2f32) }\n"),
                         "0.300000012\n")

    def test_division_by_zero_is_inf(self):
        self.assertEqual(run("fun main() { print(1.0 / 0.0) }\n"), "inf\n")
        self.assertEqual(run("fun main() { print(0.0 / 0.0) }\n"), "nan\n")

    def test_casts(self):
        self.assertEqual(run("fun main() { print(3.9 as int32) }\n"), "3\n")
        self.assertEqual(run("fun main() { print(5 as float64) }\n"), "5\n")


if __name__ == "__main__":
    unittest.main()
