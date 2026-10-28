"""How diagnostics render (MYLA-65): the caret line underlines the whole range
an error is about (the offending token for lex and parse errors, the expression
or declaration for type errors), only to the end of the first line when the
range spans lines; the `-->` position and the message stay what they were.
Notes and help lines follow the error they belong to."""
import unittest

from myla.canon import canonical_error
from myla.errors import MylaError, Note, hint
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check


def _error(source: str) -> MylaError:
    try:
        check(parse(tokenize(source)))
    except MylaError as err:
        return err
    raise AssertionError("the program was accepted")


def _render(source: str) -> str:
    return _error(source).render(source, "t.my")


def _main(*lines: str, before: str = "") -> str:
    body = "".join(f"    {line}\n" for line in lines)
    return f"{before}fun main() {{\n{body}}}\n"


class UnderlineTests(unittest.TestCase):
    def assertUnderlines(self, source: str, line: str, carets: str) -> None:
        """The diagnostic shows `line` with `carets` beneath it (before any
        notes)."""
        rendered = _render(source).splitlines()
        self.assertEqual(rendered[2:5][-2:], [line, carets], "\n".join(rendered))

    # -- the whole rendering ---------------------------------------------------

    def test_a_type_error_keeps_its_position_and_underlines_the_expression(self):
        self.assertEqual(
            _render(_main('let x = "a" + 1')),
            "type error: cannot concatenate 'str' with 'int32'\n"
            "  --> t.my:2:17\n"
            "  |\n"
            '2 |     let x = "a" + 1\n'
            "  |             ^^^^^^^",
        )

    # -- lex errors: from the error's position to where the lexer stopped -------

    def test_unexpected_character(self):
        self.assertUnderlines(_main("let x = $foo"), "2 |     let x = $foo", "  |             ^")

    def test_unterminated_string_runs_to_the_end_of_the_line(self):
        self.assertUnderlines(_main('let s = "oops'), '2 |     let s = "oops', "  |             ^^^^^")

    def test_bad_integer_suffix(self):
        self.assertUnderlines(_main("let x = 10i9"), "2 |     let x = 10i9", "  |             ^^^^")

    def test_unterminated_block_comment_stops_at_the_end_of_its_first_line(self):
        self.assertUnderlines("fun main() {}\n/* never\nclosed\n", "2 | /* never", "  | ^^^^^^^^")

    def test_bad_unicode_escape(self):
        self.assertUnderlines(_main('let s = "a\\u{12G}"'), '2 |     let s = "a\\u{12G}"',
                              "  |                ^^^^^")

    # -- parse errors: the offending token ---------------------------------------

    def test_unexpected_keyword(self):
        self.assertUnderlines(_main("let match = 1"), "2 |     let match = 1", "  |         ^^^^^")

    def test_invalid_assignment_target(self):
        self.assertUnderlines(_main("f(1) = 2"), "2 |     f(1) = 2", "  |     ^^^^")

    def test_end_of_input_gets_one_caret(self):
        self.assertUnderlines("fun main() {\n    let x = 1 +", "2 |     let x = 1 +", "  |                ^")

    # -- type errors: the node the error is about -------------------------------

    def test_argument_type_mismatch_underlines_the_argument(self):
        before = "fun add(a: int, b: int) -> int {\n    return a + b\n}\n"
        self.assertUnderlines(_main('print(add(1, "x" + "y"))', before=before),
                              '5 |     print(add(1, "x" + "y"))', "  |                  ^^^^^^^^^")

    def test_unknown_function_underlines_the_call(self):
        self.assertUnderlines(_main("let x = nope(1, 2)"), "2 |     let x = nope(1, 2)",
                              "  |             ^^^^^^^^^^")

    def test_method_call_on_a_chain(self):
        before = "struct P { x: int }\n"
        self.assertUnderlines(_main("let p = P { x: 1 }", "print(p.nope(1))", before=before),
                              "4 |     print(p.nope(1))", "  |           ^^^^^^^^^")

    def test_cast_and_pipe(self):
        self.assertUnderlines(_main('let x = "42" as int32'), '2 |     let x = "42" as int32',
                              "  |             ^^^^^^^^^^^^^")
        self.assertUnderlines(_main("print(5 |> 3)"), "2 |     print(5 |> 3)", "  |           ^^^^^^")

    def test_parentheses_belong_to_the_enclosing_expression(self):
        self.assertUnderlines(_main('let x = ("a" + 1) * 2'), '2 |     let x = ("a" + 1) * 2',
                              "  |              ^^^^^^^")
        self.assertUnderlines(_main('let x = (1 + 2) as str'), '2 |     let x = (1 + 2) as str',
                              "  |             ^^^^^^^^^^^^^^")

    def test_statement(self):
        self.assertUnderlines(_main("let x = 1", "x = 2 + 3"), "3 |     x = 2 + 3", "  |     ^^^^^^^^^")

    def test_type_annotation_with_arguments(self):
        before = "struct Box<T> { value: T }\n"
        self.assertUnderlines(before + "fun f(b: Box<int, str>) {}\nfun main() {}\n",
                              "2 | fun f(b: Box<int, str>) {}", "  |          ^^^^^^^^^^^^^")

    def test_a_declaration_spanning_lines_is_underlined_to_the_end_of_its_first_line(self):
        self.assertUnderlines("fun f(n: int) -> int {\n    print(n)\n}\nfun main() {}\n",
                              "1 | fun f(n: int) -> int {", "  | ^^^^^^^^^^^^^^^^^^^^^^")

    def test_columns_count_characters(self):
        self.assertUnderlines(_main('let x = "äö" + 1'), '2 |     let x = "äö" + 1', "  |             ^^^^^^^^")
        self.assertUnderlines("fun größe() -> int {\n    print(1)\n}\nfun main() {}\n",
                              "1 | fun größe() -> int {", "  | ^^^^^^^^^^^^^^^^^^^^")

    def test_an_interpolation_hole(self):
        self.assertUnderlines(_main('print(f"x = {nope(1)}!")'),
                              '2 |     print(f"x = {nope(1)}!")', "  |                  ^^^^^^^")

    def test_match_arm(self):
        self.assertUnderlines(_main("let n = match 1 {", "    _ => 1,", "    2 => 2,", "}"),
                              "4 |         2 => 2,", "  |         ^^^^^^")


class SpanTests(unittest.TestCase):
    def test_a_type_error_carries_the_span_of_its_node(self):
        err = _error(_main('let x = "a" + 1'))
        self.assertEqual((err.line, err.column), (2, 17))
        self.assertEqual(err.span, (2, 13, 2, 20))

    def test_a_lex_error_spans_to_where_the_lexer_stopped(self):
        err = _error(_main("let x = 0x"))
        self.assertEqual(err.span, (2, 13, 2, 15))

    def test_tokens_know_where_they_end(self):
        toks = tokenize('let größe = "ab\\n" + f"{x}"\n')
        self.assertEqual([(t.lexeme, t.end_line, t.end_column) for t in toks[:5]],
                         [("let", 1, 4), ("größe", 1, 10), ("=", 1, 12), ("ab\n", 1, 19), ("+", 1, 21)])
        # the tokens an f-string lowers to end where it ends; its holes keep their own ends
        self.assertEqual([(t.lexeme, t.column, t.end_column) for t in toks[5:]],
                         [("format", 22, 28), ("(", 22, 28), ("{}", 22, 28), (",", 22, 28),
                          ("x", 25, 26), (")", 22, 28), ("", 1, 1)])

    def test_an_error_without_a_span_gets_one_caret(self):
        err = MylaError("boom", 1, 3)
        self.assertEqual(err.render("abcdef"), "error: boom\n  --> <input>:1:3\n  |\n1 | abcdef\n  |   ^")


class NoteTests(unittest.TestCase):
    """Notes and help lines (MYLA-65)."""

    def test_a_note_shows_its_own_line(self):
        self.assertEqual(
            _render(_main("let x = 1", "x = 2")),
            "type error: cannot assign to an immutable binding (declare it with 'var')\n"
            "  --> t.my:3:7\n"
            "  |\n"
            "3 |     x = 2\n"
            "  |     ^^^^^\n"
            "note: 'x' is declared here\n"
            "  --> t.my:2:5\n"
            "  |\n"
            "2 |     let x = 1\n"
            "  |     ^^^^^^^^^",
        )

    def test_a_help_line_has_no_place(self):
        err = MylaError("boom", 1, 3, notes=[hint("did you mean 'abc'?")])
        self.assertEqual(err.render("abcdef"),
                         "error: boom\n  --> <input>:1:3\n  |\n1 | abcdef\n  |   ^\n"
                         "help: did you mean 'abc'?")

    def test_canonical_lines_follow_the_error(self):
        err = MylaError("boom", 1, 3, notes=[Note("note", "here", 2, 5, (2, 5, 2, 9)),
                                            hint("did you mean 'abc'?")])
        self.assertEqual(canonical_error(err),
                         "err 1 3 - error: boom\nnote 2 5 2:5-2:9: here\nhelp - - -: did you mean 'abc'?")

    def test_the_closest_name_is_suggested(self):
        def helps(source):
            return [(n.label, n.message) for n in _error(source).notes]
        self.assertEqual(helps(_main("let count = 1", "print(cuont)")),
                         [("help", "did you mean 'count'?")])
        # equally close names: the alphabetically first
        self.assertEqual(helps(_main("let abcd = 1", "let abce = 2", "print(abcf)")),
                         [("help", "did you mean 'abcd'?")])
        # too far, or too short to tell
        self.assertEqual(helps(_main("let count = 1", "print(cxxnt)")), [])
        self.assertEqual(helps(_main("let x = 1", "print(y)")), [])
        # `__` primitives are not suggested
        self.assertEqual(helps(_main("__exti(1)")), [])


class EditDistanceTests(unittest.TestCase):
    def test_edits(self):
        from myla.types import _edit_distance
        self.assertEqual(_edit_distance("count", "count"), 0)
        self.assertEqual(_edit_distance("cuont", "count"), 1)     # a swap
        self.assertEqual(_edit_distance("cont", "count"), 1)
        self.assertEqual(_edit_distance("coutn", "count"), 1)
        self.assertEqual(_edit_distance("kitten", "sitting"), 3)
        self.assertEqual(_edit_distance("", "abc"), 3)
        self.assertEqual(_edit_distance("ca", "abc"), 3)          # no edit after a swap
        self.assertEqual(_edit_distance("o", "ö"), 2)             # bytes: ö is two


if __name__ == "__main__":
    unittest.main()
