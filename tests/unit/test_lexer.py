"""Unit tests for the Myla lexer (docs/Language/Lexical-structure.md)."""
import unittest

from myla.errors import LexError
from myla.lexer import tokenize
from myla.tokens import TokenKind as T


def kinds(source):
    return [tok.kind for tok in tokenize(source)]


class TestBasicTokens(unittest.TestCase):
    def test_empty_source_is_just_eof(self):
        toks = tokenize("")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].kind, T.EOF)

    def test_whitespace_only(self):
        self.assertEqual(kinds("   \t  "), [T.EOF])

    def test_single_operators(self):
        self.assertEqual(
            kinds("+ - * / % < > ! = ( ) { } [ ] , : . #"),
            [
                T.PLUS, T.MINUS, T.STAR, T.SLASH, T.PERCENT,
                T.LT, T.GT, T.BANG, T.ASSIGN,
                T.LPAREN, T.RPAREN, T.LBRACE, T.RBRACE, T.LBRACKET, T.RBRACKET,
                T.COMMA, T.COLON, T.DOT, T.HASH, T.EOF,
            ],
        )

    def test_two_char_operators(self):
        self.assertEqual(
            kinds("-> .. == != <= >= && ||"),
            [T.ARROW, T.DOTDOT, T.EQ, T.NE, T.LE, T.GE, T.AND, T.OR, T.EOF],
        )

    def test_greedy_match_eq_vs_assign(self):
        self.assertEqual(kinds("== ="), [T.EQ, T.ASSIGN, T.EOF])

    def test_range_is_not_two_dots(self):
        self.assertEqual(kinds("0..5"), [T.INT, T.DOTDOT, T.INT, T.EOF])


class TestKeywordsAndIdents(unittest.TestCase):
    def test_keywords(self):
        self.assertEqual(
            kinds("let var fun return struct typealias if else while for in"),
            [
                T.LET, T.VAR, T.FUN, T.RETURN, T.STRUCT, T.TYPEALIAS,
                T.IF, T.ELSE, T.WHILE, T.FOR, T.IN, T.EOF,
            ],
        )

    def test_sized_type_keywords(self):
        self.assertEqual(
            kinds("int8 int16 int32 int64 uint8 uint16 uint32 uint64 bool str"),
            [
                T.INT8, T.INT16, T.INT32, T.INT64,
                T.UINT8, T.UINT16, T.UINT32, T.UINT64,
                T.BOOL, T.STR, T.EOF,
            ],
        )

    def test_int_is_identifier_not_keyword(self):
        # `int` is a built-in alias for int32, lexed as an ident.
        toks = tokenize("int")
        self.assertEqual(toks[0].kind, T.IDENT)
        self.assertEqual(toks[0].value, "int")

    def test_bool_literals_carry_value(self):
        toks = tokenize("true false")
        self.assertEqual(toks[0].kind, T.TRUE)
        self.assertIs(toks[0].value, True)
        self.assertEqual(toks[1].kind, T.FALSE)
        self.assertIs(toks[1].value, False)

    def test_identifier_value_and_underscores(self):
        toks = tokenize("foo_bar _x x123")
        self.assertEqual([t.kind for t in toks[:3]], [T.IDENT, T.IDENT, T.IDENT])
        self.assertEqual([t.value for t in toks[:3]], ["foo_bar", "_x", "x123"])


class TestIntLiterals(unittest.TestCase):
    def test_plain_int(self):
        toks = tokenize("42")
        self.assertEqual(toks[0].kind, T.INT)
        self.assertEqual(toks[0].value, 42)
        self.assertIsNone(toks[0].suffix)

    def test_int_with_suffixes(self):
        for text, suffix in [("255u8", "u8"), ("123i64", "i64"), ("0i8", "i8")]:
            toks = tokenize(text)
            self.assertEqual(toks[0].kind, T.INT, text)
            self.assertEqual(toks[0].suffix, suffix, text)

    def test_value_of_suffixed_literal(self):
        toks = tokenize("255u8")
        self.assertEqual(toks[0].value, 255)
        self.assertEqual(toks[0].suffix, "u8")

    def test_invalid_suffix(self):
        with self.assertRaises(LexError) as ctx:
            tokenize("5u7")
        self.assertIn("suffix", ctx.exception.message)

    def test_digits_abutting_identifier_is_error(self):
        with self.assertRaises(LexError):
            tokenize("5x")


class TestStrings(unittest.TestCase):
    def test_simple_string(self):
        toks = tokenize('"hello"')
        self.assertEqual(toks[0].kind, T.STRING)
        self.assertEqual(toks[0].value, "hello")

    def test_empty_string(self):
        toks = tokenize('""')
        self.assertEqual(toks[0].value, "")

    def test_escapes(self):
        toks = tokenize(r'"a\nb\tc\\d\"e"')
        self.assertEqual(toks[0].value, 'a\nb\tc\\d"e')

    def test_unterminated_string(self):
        with self.assertRaises(LexError):
            tokenize('"oops')

    def test_newline_in_string_is_error(self):
        with self.assertRaises(LexError):
            tokenize('"line\nbreak"')

    def test_invalid_escape(self):
        with self.assertRaises(LexError):
            tokenize(r'"bad \q escape"')


class TestCharLiterals(unittest.TestCase):
    def test_ascii_char(self):
        toks = tokenize("'a'")
        self.assertEqual(toks[0].kind, T.CHAR)
        self.assertEqual(toks[0].value, 97)

    def test_escapes(self):
        for src, byte in [(r"'\n'", 10), (r"'\t'", 9), (r"'\r'", 13),
                          (r"'\\'", 92), (r"'\''", 39), (r"'\0'", 0)]:
            self.assertEqual(tokenize(src)[0].value, byte, src)

    def test_empty_char_is_error(self):
        with self.assertRaises(LexError):
            tokenize("''")

    def test_multibyte_char_is_error(self):
        with self.assertRaises(LexError):
            tokenize("'ab'")

    def test_non_ascii_char_is_scalar(self):
        # v0.5.3: char literals are Unicode scalars, not bytes.
        self.assertEqual(tokenize("'é'")[0].value, 0xE9)
        self.assertEqual(tokenize("'λ'")[0].value, 0x3BB)
        self.assertEqual(tokenize("'😀'")[0].value, 0x1F600)

    def test_unicode_escape(self):
        self.assertEqual(tokenize(r"'\u{1F600}'")[0].value, 0x1F600)
        self.assertEqual(tokenize(r"'\u{0}'")[0].value, 0)
        self.assertEqual(tokenize(r"'\u{a5}'")[0].value, 0xA5)

    def test_invalid_unicode_escape(self):
        for bad in [r"'\u{110000}'", r"'\u{D800}'", r"'\u{}'", r"'\uABCD'",
                    r"'\u{ZZ}'"]:
            with self.assertRaises(LexError):
                tokenize(bad)

    def test_invalid_char_escape(self):
        with self.assertRaises(LexError):
            tokenize(r"'\q'")


class TestComments(unittest.TestCase):
    def test_line_comment(self):
        self.assertEqual(kinds("1 // ignored\n2"), [T.INT, T.NEWLINE, T.INT, T.EOF])

    def test_block_comment(self):
        self.assertEqual(kinds("1 /* a\n b */ 2"), [T.INT, T.INT, T.EOF])

    def test_unterminated_block_comment(self):
        with self.assertRaises(LexError):
            tokenize("/* never closed")


class TestNewlines(unittest.TestCase):
    def test_leading_newlines_suppressed(self):
        self.assertEqual(kinds("\n\n1"), [T.INT, T.EOF])

    def test_consecutive_newlines_coalesced(self):
        self.assertEqual(kinds("1\n\n\n2"), [T.INT, T.NEWLINE, T.INT, T.EOF])

    def test_trailing_newline_dropped(self):
        self.assertEqual(kinds("1\n"), [T.INT, T.EOF])


class TestPositions(unittest.TestCase):
    def test_line_and_column_tracking(self):
        toks = tokenize("let x\n  y")
        let_tok, x_tok = toks[0], toks[1]
        self.assertEqual((let_tok.line, let_tok.column), (1, 1))
        self.assertEqual((x_tok.line, x_tok.column), (1, 5))
        # after the newline token, `y` is on line 2, col 3
        y_tok = toks[3]
        self.assertEqual(y_tok.kind, T.IDENT)
        self.assertEqual((y_tok.line, y_tok.column), (2, 3))

    def test_error_position(self):
        with self.assertRaises(LexError) as ctx:
            tokenize("a\n  $")
        self.assertEqual(ctx.exception.line, 2)
        self.assertEqual(ctx.exception.column, 3)


class TestRealProgram(unittest.TestCase):
    def test_function_declaration(self):
        src = "fun add(a: int, b: int) -> int {\n    return a + b\n}\n"
        result = kinds(src)
        expected = [
            T.FUN, T.IDENT, T.LPAREN,
            T.IDENT, T.COLON, T.IDENT, T.COMMA,
            T.IDENT, T.COLON, T.IDENT, T.RPAREN,
            T.ARROW, T.IDENT, T.LBRACE, T.NEWLINE,
            T.RETURN, T.IDENT, T.PLUS, T.IDENT, T.NEWLINE,
            T.RBRACE, T.EOF,
        ]
        self.assertEqual(result, expected)

    def test_attribute_tokens(self):
        self.assertEqual(
            kinds("#test(1, 2)[3]"),
            [
                T.HASH, T.IDENT, T.LPAREN, T.INT, T.COMMA, T.INT, T.RPAREN,
                T.LBRACKET, T.INT, T.RBRACKET, T.EOF,
            ],
        )


if __name__ == "__main__":
    unittest.main()
