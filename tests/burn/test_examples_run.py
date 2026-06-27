"""Burn tests: run each example program and assert its stdout.

These pin down end-to-end behavior (lexer -> parser -> checker -> interpreter)
and double as living documentation of what each example prints.
"""
import io
import os
import unittest

from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check

EXAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "examples")
)

# filename -> expected stdout
EXPECTED = {
    "hello.my": "Hello from Myla!\n",
    "variables.my": "10\nAnn\ntrue\n2\n",
    "functions.my": "5\n120\n",
    "loops.my": "10\n3\n2\n1\ntrue\n",
    "control_flow.my": "negative\nzero\npositive\ntrue\ntrue\ntrue\n",
    "structs.my": "3\n4\n7\n100\n3\n",
    "attributes.my": "5\n0\n",
}


def run_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    checker = check(parse(tokenize(source)))
    out = io.StringIO()
    Interpreter(checker, out).run()
    return out.getvalue()


class TestExamplesRun(unittest.TestCase):
    pass


def _make(name: str, expected: str):
    def test(self):
        path = os.path.join(EXAMPLES_DIR, name)
        self.assertTrue(os.path.exists(path), f"missing example {name}")
        self.assertEqual(run_file(path), expected)
    return test


for _name, _expected in EXPECTED.items():
    setattr(TestExamplesRun, f"test_{_name.replace('.', '_')}", _make(_name, _expected))


if __name__ == "__main__":
    unittest.main()
