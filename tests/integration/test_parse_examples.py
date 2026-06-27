"""Integration test: every example program lexes and parses without error.

These `.my` files are the project's burn-tests (docs roadmap v0.0.1); once the
interpreter exists they will also be executed and checked against expected
output. For now we assert they form a valid `Program` with at least one
function declaration.
"""
import os
import unittest

from myla import ast
from myla.lexer import tokenize
from myla.parser import parse

_EXAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "examples")
)


def _example_files():
    return sorted(
        os.path.join(_EXAMPLES_DIR, name)
        for name in os.listdir(_EXAMPLES_DIR)
        if name.endswith(".my")
    )


class TestParseExamples(unittest.TestCase):
    def test_examples_directory_is_not_empty(self):
        self.assertTrue(_example_files(), "no example .my files found")

    def test_all_examples_parse(self):
        for path in _example_files():
            with self.subTest(example=os.path.basename(path)):
                with open(path, "r", encoding="utf-8") as fh:
                    source = fh.read()
                program = parse(tokenize(source))
                self.assertIsInstance(program, ast.Program)
                self.assertTrue(program.decls, "expected at least one declaration")
                self.assertTrue(
                    any(isinstance(d, ast.FunDecl) for d in program.decls),
                    "expected at least one function declaration",
                )


if __name__ == "__main__":
    unittest.main()
