"""More than one error per run (MYLA-65, D80).

The parser records an error and resumes at the next statement, impl member or
declaration; the checker checks every function's attributes and body on its
own once the declarations are consistent. The first error is the one a
single-error run reported; the others follow it in `err.more`, and the CLI
prints them all, then a summary line."""
import os
import subprocess
import sys
import tempfile
import unittest

from myla.cli import report_text
from myla.errors import MAX_ERRORS, LexError, MylaError, ParseError, TypeCheckError
from myla.lexer import tokenize
from myla.loader import link
from myla.parser import parse
from myla.types import check

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def _errors(source: str) -> list[MylaError]:
    try:
        check(parse(tokenize(source)))
    except MylaError as err:
        return [err, *err.more]
    raise AssertionError("the program was accepted")


def _lines(source: str) -> list[int]:
    return [e.line for e in _errors(source)]


class ParseRecoveryTests(unittest.TestCase):
    def test_the_next_statement_and_the_next_function_are_parsed(self):
        src = ("fun main() {\n    let = 1\n    let y = 2\n    y = = 3\n}\n"
               "fun g() {\n    print(1 +)\n}\n")
        errs = _errors(src)
        self.assertTrue(all(isinstance(e, ParseError) for e in errs))
        self.assertEqual([(e.line, e.message) for e in errs], [
            (2, "expected variable name, found '='"),
            (4, "expected an expression, found '='"),
            (7, "expected an expression, found ')'"),
        ])

    def test_the_first_error_is_the_one_a_single_error_run_reported(self):
        src = "fun main() {\n    let = 1\n    let = 2\n}\n"
        first = _errors(src)[0]
        self.assertEqual((first.line, first.column, first.span), (2, 9, (2, 9, 2, 10)))
        self.assertEqual(first.render(src, "t.my").splitlines()[0],
                         "parse error: expected variable name, found '='")

    def test_an_error_in_a_header_skips_that_declaration(self):
        src = "fun f(a int) -> int {\n    return a\n}\nfun main() {\n    let = 1\n}\n"
        self.assertEqual([(e.line, e.message) for e in _errors(src)], [
            (1, "expected ':', found 'int'"),
            (5, "expected variable name, found '='"),
        ])

    def test_a_statement_spanning_lines_gives_one_error(self):
        src = "fun main() {\n    print(f(1 +,\n        2))\n    let = 1\n}\n"
        self.assertEqual(_lines(src), [2, 4])

    def test_an_unclosed_parenthesis_ends_at_the_next_statement(self):
        # the newline the `)` is missing before starts on line 3
        src = "fun main() {\n    let x = (1 + 2\n    let y = = 3\n}\n"
        self.assertEqual([(e.line, e.column) for e in _errors(src)], [(3, 1), (3, 13)])

    def test_one_error_per_statement(self):
        errs = _errors("fun main() {\n    let x = = = 1; let = 2\n}\n")
        self.assertEqual([(e.line, e.column) for e in errs], [(2, 13), (2, 24)])

    def test_a_missing_brace_resumes_at_the_next_declaration(self):
        src = ("fun f() {\n    if true {\n        let x = 1\n}\n"
               "fun g() {\n    let = 2\n}\n")
        self.assertEqual([(e.line, e.message) for e in _errors(src)], [
            (5, "expected an expression, found 'fun'"),
            (6, "expected variable name, found '='"),
        ])

    def test_a_missing_brace_after_an_earlier_error_is_reported(self):
        src = ("fun f() {\n    let = 1\n    if true {\n        print(1)\n\n"
               "fun g() {\n    let = 2\n}\n")
        self.assertEqual([(e.line, e.message) for e in _errors(src)], [
            (2, "expected variable name, found '='"),
            (6, "expected an expression, found 'fun'"),
            (7, "expected variable name, found '='"),
        ])

    def test_impl_members_are_parsed_after_an_error(self):
        src = ("struct S { a: int }\nimpl S {\n    fun f(self) -> int {\n        return = 1\n    }\n"
               "    let x = 1\n    fun g(self) -> int {\n        return self.a +\n    }\n}\n"
               "fun main() {\n    let = 1\n}\n")
        errs = _errors(src)
        self.assertEqual([e.line for e in errs], [4, 6, 9, 12])
        self.assertEqual(errs[1].message, "expected a method ('fun ...') in impl block, found 'let'")

    def test_an_error_in_a_struct_body(self):
        src = "struct P {\n    x int,\n    y: int,\n}\nfun main() {\n    let = 1\n}\n"
        self.assertEqual(_lines(src), [2, 6])

    def test_an_error_at_the_end_of_the_input(self):
        self.assertEqual(_lines("fun main() {\n    let x = (1"), [2])

    def test_at_most_max_errors(self):
        src = "fun main() {\n" + "    let = 1\n" * (MAX_ERRORS + 5) + "}\n"
        self.assertEqual(_lines(src), list(range(2, MAX_ERRORS + 2)))

    def test_a_lex_error_stays_single(self):
        errs = _errors("fun main() {\n    let = 1\n    let s = $\n}\n")
        self.assertEqual(len(errs), 1)
        self.assertIsInstance(errs[0], LexError)


class CheckRecoveryTests(unittest.TestCase):
    def test_every_function_is_checked(self):
        src = ("fun f() -> int {\n    return \"a\"\n}\n"
               "fun g() {\n    let x: int = true\n    let y: int = \"x\"\n}\n"
               "struct S { a: int }\nimpl S {\n    fun m(self) -> int {\n        return nope\n    }\n}\n"
               "fun main() {\n    print(1 + \"x\")\n}\n")
        errs = _errors(src)
        self.assertTrue(all(isinstance(e, TypeCheckError) for e in errs))
        # free functions in source order, then methods (one error each)
        self.assertEqual([e.line for e in errs], [2, 5, 15, 11])

    def test_attribute_errors_come_first(self):
        src = ("fun main() {\n    let x: int = true\n}\n"
               "#test(1, 2)[3]\nfun h(a: int) -> int {\n    return a\n}\n")
        self.assertEqual([(e.line, e.message) for e in _errors(src)][0],
                         (4, "'#test' expects 1 argument(s), got 2"))
        self.assertEqual(_lines(src), [4, 2])

    def test_bodies_are_checked_after_a_declaration_error(self):
        # MYLA-110: the duplicate is left out, and main is still checked
        src = "fun f() {}\nfun f() {}\nfun main() {\n    let x: int = true\n}\n"
        errs = _errors(src)
        self.assertEqual([e.message for e in errs], [
            "duplicate top-level declaration 'f'",
            "cannot assign value of type 'bool' to binding of type 'int32'",
        ])

    def test_a_failed_function_leaves_no_state_behind(self):
        # the error inside the loop must not leave `b` inside a loop
        src = ("fun a() {\n    while true {\n        let x: int = \"s\"\n    }\n}\n"
               "fun b() {\n    break\n}\nfun main() {}\n")
        errs = _errors(src)
        self.assertEqual([e.line for e in errs], [3, 7])
        self.assertIn("break", errs[1].message)

    def test_at_most_max_errors(self):
        funcs = "".join(f"fun f{i}() {{\n    let x: int = true\n}}\n" for i in range(MAX_ERRORS + 3))
        self.assertEqual(len(_errors(funcs + "fun main() {}\n")), MAX_ERRORS)

    def test_each_error_names_its_module(self):
        root = tempfile.mkdtemp(prefix="myla_errs_")
        with open(os.path.join(root, "m.my"), "w") as fh:
            fh.write("pub fun f() -> int {\n    return \"s\"\n}\n")
        with open(os.path.join(root, "main.my"), "w") as fh:
            fh.write("from .m import f\nfun main() {\n    let x: int = true\n}\n")
        with self.assertRaises(TypeCheckError) as ctx:
            check(link(os.path.join(root, "main.my")))
        errs = [ctx.exception, *ctx.exception.more]
        self.assertEqual([(os.path.basename(e.path), e.line) for e in errs], [("main.my", 3), ("m.my", 2)])


class ReportTests(unittest.TestCase):
    SRC = "fun f() -> int {\n    return \"a\"\n}\nfun main() {\n    let x: int = true\n}\n"

    def test_every_error_then_a_summary(self):
        err = _errors(self.SRC)[0]
        self.assertEqual(report_text(err, "t.my", self.SRC),
                         err.render(self.SRC, "t.my") + "\n\n" + err.more[0].render(self.SRC, "t.my")
                         + "\n\nerror: aborting due to 2 previous errors")

    def test_a_single_error_has_no_summary(self):
        src = "fun main() {\n    let x: int = true\n}\n"
        err = _errors(src)[0]
        self.assertEqual(report_text(err, "t.my", src), err.render(src, "t.my"))

    def test_the_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.my")
            with open(path, "w") as fh:
                fh.write(self.SRC)
            proc = subprocess.run([sys.executable, os.path.join(_REPO, "myla.py"), "check", path],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stderr.count("type error: "), 2)
            self.assertTrue(proc.stderr.endswith("\n\nerror: aborting due to 2 previous errors\n"), proc.stderr)
            proc = subprocess.run([sys.executable, os.path.join(_REPO, "myla.py"), "check", "--canonical", path],
                                  capture_output=True, text=True)
            self.assertEqual(proc.stdout, "err 2 5 type\nerr 5 5 type\n")


if __name__ == "__main__":
    unittest.main()
