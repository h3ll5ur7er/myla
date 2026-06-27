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
    "tuples.my": "7\nseven\n42\n3\n2\n6\n100\n15\n25\n5\n",
    "enums.my": "12\n12\n0\nwarm\ncool\nbig circle\nsmall circle\nother\n",
    "types_and_aliases.my": "0\n42\n9\n",
    "recursion.my": "6\n6\n3\n12\n10\n10\nbalanced pair\nbranch\n",
    "regressions.my": "zero\n5\n5\nminus one\n1\n",
    "generics.my": "42\nmyla\n10\n2\n1\n16\n",
    "generic-types.my": "42\n1\n9\n-1\n60\n3\n",
    "option-result.my": "ok\ndivide by zero\n107\n-1\n42\n",
}


def run_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    checker = check(parse(tokenize(source)))
    out = io.StringIO()
    Interpreter(checker, out).run()
    return out.getvalue()


def _example_files() -> set[str]:
    return {f for f in os.listdir(EXAMPLES_DIR) if f.endswith(".my")}


class TestExamplesRun(unittest.TestCase):
    def test_every_example_has_expected_output(self):
        # Convention: every example is pinned by its expected stdout here, so a
        # new feature example can't land without run coverage.
        missing = _example_files() - set(EXPECTED)
        self.assertFalse(missing, f"examples without expected output: {sorted(missing)}")

    def test_no_stale_expectations(self):
        stale = set(EXPECTED) - _example_files()
        self.assertFalse(stale, f"expected output for missing examples: {sorted(stale)}")


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
