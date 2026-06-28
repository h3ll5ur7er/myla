"""Unit tests for f-string interpolation (v0.5.6, D58).

`f"…{expr}…"` is pure lexer sugar: it lowers *in place* to a `format(fmt, args…)`
call, so there is no new token, AST node, checker rule, or runtime. These tests
pin the token-level desugaring and a few interpreter end-to-end results; native
parity lives in the burn suite (examples/interpolation.my).
"""
import io
import unittest

from myla.errors import LexError, TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.tokens import TokenKind as T
from myla.types import check


def lower(source: str) -> str:
    """The desugared token stream of a single f-string, as a readable string."""
    out = []
    for tok in tokenize(source):
        if tok.kind is T.EOF:
            continue
        if tok.kind is T.STRING:
            out.append(repr(tok.value))
        else:
            out.append(tok.lexeme)
    return " ".join(out)


def run_src(src: str) -> str:
    out = io.StringIO()
    Interpreter(check(parse(tokenize(src))), out).run()
    return out.getvalue()


class TestDesugar(unittest.TestCase):
    def test_two_holes(self):
        self.assertEqual(
            lower('f"{name} = {value}"'),
            "format ( '{} = {}' , name , value )",
        )

    def test_no_holes_is_plain_format(self):
        self.assertEqual(lower('f"hello"'), "format ( 'hello' )")

    def test_expression_hole(self):
        self.assertEqual(lower('f"{a + 1}"'), "format ( '{}' , a + 1 )")

    def test_literal_braces_are_preserved(self):
        # `{{`/`}}` pass through to the format string verbatim (format renders
        # them as single braces); only `{expr}` becomes a `{}` placeholder.
        self.assertEqual(
            lower('f"set {{ {x} }}"'), "format ( 'set {{ {} }}' , x )"
        )

    def test_nested_string_in_hole(self):
        # A quote inside a hole opens a nested string; its `}`/`"` don't end the
        # hole or the f-string.
        self.assertEqual(lower('f"{m["k"]}"'), "format ( '{}' , m [ 'k' ] )")

    def test_escapes_apply_to_literal_text(self):
        self.assertEqual(lower(r'f"a\tb\n"'), "format ( 'a\\tb\\n' )")

    def test_nested_fstring(self):
        self.assertEqual(
            lower('f"{f"{x}"}"'), "format ( '{}' , format ( '{}' , x ) )"
        )


class TestErrors(unittest.TestCase):
    def test_empty_hole(self):
        with self.assertRaises(LexError) as ctx:
            tokenize('f"{}"')
        self.assertIn("empty '{}' hole", str(ctx.exception))

    def test_single_close_brace(self):
        with self.assertRaises(LexError) as ctx:
            tokenize('f"a}b"')
        self.assertIn("single '}'", str(ctx.exception))

    def test_unterminated_is_single_line(self):
        with self.assertRaises(LexError) as ctx:
            tokenize('f"oops\n"')
        self.assertIn("unterminated f-string literal", str(ctx.exception))

    def test_bad_escape(self):
        with self.assertRaises(LexError) as ctx:
            tokenize(r'f"\q"')
        self.assertIn("invalid escape sequence", str(ctx.exception))

    def test_unprintable_hole_type_rejected(self):
        # The hole inherits format's printable-type rule.
        src = (
            "fun main() {\n"
            "    let xs = [1, 2]\n"
            "    print(f\"{xs}\")\n"
            "}\n"
        )
        with self.assertRaises(TypeCheckError) as ctx:
            check(parse(tokenize(src)))
        self.assertIn("cannot render", str(ctx.exception))


class TestInterpreter(unittest.TestCase):
    def test_basic_interpolation(self):
        src = (
            "fun main() {\n"
            "    let name = \"myla\"\n"
            "    let n = 42\n"
            "    print(f\"{name} = {n}\")\n"
            "}\n"
        )
        self.assertEqual(run_src(src), "myla = 42\n")

    def test_literal_braces_render_single(self):
        src = (
            "fun main() {\n"
            "    let x = 1\n"
            "    print(f\"{{ {x} }}\")\n"
            "}\n"
        )
        self.assertEqual(run_src(src), "{ 1 }\n")

    def test_hole_with_call_and_arithmetic(self):
        src = (
            "fun double(x: int32) -> int32 { return x * 2 }\n"
            "fun main() {\n"
            "    print(f\"{double(3)} and {1 + 2}\")\n"
            "}\n"
        )
        self.assertEqual(run_src(src), "6 and 3\n")


if __name__ == "__main__":
    unittest.main()
