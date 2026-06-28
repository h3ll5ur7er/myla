"""Unit tests for the `char` type (v0.5.3a, D25): Unicode-scalar literals, the
`char` type's defaulting/flexibility, `as` conversions, comparisons, the shared
UTF-8 renderer, and interpreter semantics."""
import io
import unittest

from myla import ast
from myla.errors import TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import CHAR, CharType, IntType, char_utf8_bytes, check


def run(src: str) -> str:
    out = io.StringIO()
    Interpreter(check(parse(tokenize(src))), out).run()
    return out.getvalue()


def first_init_type(src: str):
    prog = parse(tokenize(src))
    check(prog)
    return prog.decls[0].body.statements[0].init.resolved_type


class TestCharChecking(unittest.TestCase):
    def test_literal_defaults_to_char(self):
        self.assertEqual(first_init_type("fun main() { let c = 'a' }\n"), CHAR)
        self.assertEqual(first_init_type("fun main() { let c = '\\u{3BB}' }\n"), CHAR)

    def test_annotation(self):
        check(parse(tokenize("fun main() { let c: char = 'z' }\n")))

    def test_ascii_literal_flexible_to_int(self):
        # An ASCII char literal can stand in for a byte/integer (D42).
        self.assertEqual(
            first_init_type("fun main() { let b: uint8 = 'a' }\n"), IntType(8, False))
        check(parse(tokenize(
            'fun main() { let s = "hi"\n print(s[0] == \'h\') }\n')))

    def test_non_ascii_not_flexible_to_int(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize("fun main() { let b: uint8 = '\\u{3BB}' }\n")))

    def test_no_char_arithmetic(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize("fun main() { print('a' + 'b') }\n")))

    def test_comparisons_yield_bool(self):
        check(parse(tokenize("fun main() { print('a' < 'b') }\n")))
        check(parse(tokenize("fun main() { print('a' == 'a') }\n")))

    def test_int_literal_is_not_a_char(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize("fun main() { let c: char = 65 }\n")))

    def test_casts(self):
        check(parse(tokenize("fun main() { print('a' as uint32) }\n")))
        check(parse(tokenize("fun main() { print(97 as char) }\n")))
        check(parse(tokenize("fun main() { print('a' as char) }\n")))

    def test_char_float_cast_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize("fun main() { print('a' as float64) }\n")))
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize("fun main() { print(1.5f64 as char) }\n")))

    def test_char_map_key(self):
        check(parse(tokenize(
            "fun main() { var m: [char: int] = [:]\n m['x'] = 1\n print(m['x']) }\n")))


class TestCharUtf8(unittest.TestCase):
    def test_encode_ranges(self):
        self.assertEqual(char_utf8_bytes(0x61), b"a")
        self.assertEqual(char_utf8_bytes(0xA5), "¥".encode("utf-8"))
        self.assertEqual(char_utf8_bytes(0x3BB), "λ".encode("utf-8"))
        self.assertEqual(char_utf8_bytes(0x1F600), "😀".encode("utf-8"))

    def test_matches_python_utf8(self):
        for cp in (0, 1, 0x7F, 0x80, 0x7FF, 0x800, 0xFFFF, 0x10000, 0x10FFFF):
            self.assertEqual(char_utf8_bytes(cp), chr(cp).encode("utf-8"))


class TestCharInterpreter(unittest.TestCase):
    def test_print_glyph(self):
        self.assertEqual(run("fun main() { print('a') }\n"), "a\n")
        self.assertEqual(run("fun main() { print('\\u{3BB}') }\n"), "λ\n")
        self.assertEqual(run("fun main() { print('\\u{1F600}') }\n"), "😀\n")

    def test_comparisons(self):
        self.assertEqual(run("fun main() { print('a' < 'b') }\n"), "true\n")
        self.assertEqual(run("fun main() { print('b' < 'a') }\n"), "false\n")
        self.assertEqual(run("fun main() { print('a' == 'a') }\n"), "true\n")

    def test_round_trip_casts(self):
        self.assertEqual(run("fun main() { print('a' as uint32) }\n"), "97\n")
        self.assertEqual(run("fun main() { print(955 as char) }\n"), "λ\n")

    def test_format(self):
        self.assertEqual(
            run("fun main() { print(format(\"[{}]\", '\\u{3BB}')) }\n"), "[λ]\n")

    def test_match(self):
        src = ("fun main() { let c: char = 'b'\n"
               "  match c { 'a' => print(1), 'b' => print(2), _ => print(0) } }\n")
        self.assertEqual(run(src), "2\n")


class TestCharsBuiltin(unittest.TestCase):
    def test_returns_char_list(self):
        from myla.types import ListType
        prog = parse(tokenize('fun main() { let cs = chars("hi") }\n'))
        check(prog)
        self.assertEqual(
            prog.decls[0].body.statements[0].init.resolved_type, ListType(CHAR))

    def test_rejects_non_string(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize("fun main() { let cs = chars(5) }\n")))

    def test_decodes_ascii_codepoints(self):
        src = ('fun main() {\n'
               '  for c in chars("abc") { print(c as uint32) } }\n')
        self.assertEqual(run(src), "97\n98\n99\n")

    def test_decodes_multibyte(self):
        # "héλ😀": 1+2+2+4 = 9 UTF-8 bytes, but 4 scalars.
        src = ('fun main() {\n'
               '  let s = "héλ😀"\n'
               '  print(len(s))\n'           # byte length
               '  print(len(chars(s)))\n'    # scalar count
               '  for c in chars(s) { print(c as uint32) } }\n')
        self.assertEqual(run(src), "9\n4\n104\n233\n955\n128512\n")

    def test_empty(self):
        self.assertEqual(run('fun main() { print(len(chars(""))) }\n'), "0\n")


if __name__ == "__main__":
    unittest.main()
