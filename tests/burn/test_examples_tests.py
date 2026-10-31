"""Burn test enforcing the project's `#test` convention for examples.

Convention (see README): every `.my` example must (a) have all of its embedded
`#test` cases pass, and (b) attach at least one `#test` to every value-returning
function. Entry points / void helpers are exempt (they cannot be unit-tested).

Once Myla is self-hosting, these in-language tests are the regression suite that
guards the compiler against breakage, so we keep them green from day one.
"""
import os
import unittest

from myla import ast
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check

EXAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "examples")
)


def _example_files() -> list[str]:
    return sorted(f for f in os.listdir(EXAMPLES_DIR) if f.endswith(".my"))


def _has_test_attr(decl: ast.FunDecl) -> bool:
    return any(a.name == "test" for a in decl.attributes)


class TestExamplesTestSuite(unittest.TestCase):
    def test_there_are_examples(self):
        self.assertTrue(_example_files(), "no example .my files found")

    def test_every_value_returning_function_is_tested(self):
        for name in _example_files():
            with open(os.path.join(EXAMPLES_DIR, name), encoding="utf-8") as fh:
                program = parse(tokenize(fh.read()))
            for decl in program.decls:
                if not isinstance(decl, ast.FunDecl) or decl.ret_type is None:
                    continue
                # Generic functions have no single concrete instantiation, so
                # they can't carry a `#test`; they are covered through tested
                # concrete wrappers instead.
                if decl.type_params:
                    continue
                # `#test` can't run an async function (D89); its example's
                # output covers it
                if decl.is_async:
                    continue
                self.assertTrue(
                    _has_test_attr(decl),
                    f"{name}: function '{decl.name}' returns a value but has "
                    f"no #test case (project convention requires one)",
                )

    def test_all_embedded_tests_pass(self):
        total = 0
        for name in _example_files():
            with open(os.path.join(EXAMPLES_DIR, name), encoding="utf-8") as fh:
                checker = check(parse(tokenize(fh.read())))
            results = Interpreter(checker).run_tests()
            total += len(results)
            for r in results:
                self.assertTrue(r.passed, f"{name}: {r.function} #{r.index}: {r.detail}")
        self.assertGreater(total, 0, "expected at least one #test across the examples")


if __name__ == "__main__":
    unittest.main()
