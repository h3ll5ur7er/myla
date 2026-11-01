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
    "functions.my": "5\n120\n120\ntrue\n",
    "loops.my": "10\n3\n2\n1\ntrue\n",
    "control_flow.my": "negative\nzero\npositive\ntrue\ntrue\ntrue\n",
    "structs.my": "3\n4\n7\n100\n3\n",
    "attributes.my": "5\n0\n",
    "tuples.my": "7\nseven\n42\n3\n2\n6\n100\n15\n25\n5\n",
    "unicode.my": "6\n6\u20ac\n{6}\n3\ntrue\n\"\nit's \U0001F600\n",
    "enums.my": "12\n12\n0\nwarm\ncool\nbig circle\nsmall circle\nother\n",
    "types_and_aliases.my": "0\n42\n9\n",
    "recursion.my": "6\n6\n3\n12\n10\n10\nbalanced pair\nbranch\n",
    "regressions.my": "zero\n5\n5\nminus one\n1\n",
    "generics.my": "42\nmyla\n10\n2\n1\n16\n",
    "generic-types.my": "42\n1\n9\n-1\n60\n3\n",
    "option-result.my": "ok\ndivide by zero\n107\n-1\n42\n",
    "operators.my": "255\n8\n14\n6\n255\n16\n-8\n15\n1\n-56\n30\n11\n",
    "constants.my": "4096\n4096\n255\ntrue\n64\n2\n5\nmyla\n",
    "lists.my": "3\n1\n6\n6\n10\n3\n99\n4\n20\n5\n6\n16\n16\n4\n",
    "maps.my": "6\n2\n3\n3\n1\n10\n4\n3\nfalse\ntrue\n3\n17\n100\n2\n",
    "strings.my": ("4\n77\n97\n5\n98\n3\n198\n10\n1\n1\n0\n"
                   "Hello, world!\nabc\n2 + 3 = 5\nlen: 5\ntrue and false\n"
                   "Hello, world!\n0123456789\na-b-c\n"),
    "methods.my": "1\n2\n12\n12\nfalse\n10\ntrue\n42\n4\n",
    "closures.my": ("36\n15\nhi, world\n24\n16\n18\n107\n60\n"
                    "6\n100\n42\n"),
    "pipelines.my": "11\n8\n21\n14\n15\n42\n18\n11\n12\n20\n",
    "traits.my": "4\n6\ntrue\ntrue\nvec\ntrue\nfalse\ntrue\ntrue\n60\n3\n4\n8\n3\n",
    "floats.my": ("0.5\n3.1415926535897931\n3.75\n3.5\n1.5\n-3.1415926535897931\n"
                  "0.30000000000000004\n0.300000012\ninf\ntrue\nfalse\n9\n3\n3\n"),
    "chars.my": "a\nλ\n😀\ntrue\nfalse\n65\nλ\ntrue\n2\n1\n5\n3\n104\n233\n955\n",
    "generic_traits.my": "0\n1\n-1\n0\n1\n-1\n",
    "interpolation.my": ("myla scored 42\n2 + 3 = 5\nset is { 1, 2 }\n"
                         "main.my:3:12: there is no error, this is just a test\n"),
    "traits_on_builtins.my": ("49\nhaha 67\n42\nI'm a teapot\nThis is not the error you are looking for. It is the answer to life, the universe, and everything.\nThis is not the error you are looking for. It is 13\nThis is not the error you are looking for. It is 15\nSuccess\n"),
    "semicolons.my": "12\nsize\n7\n15\n21\n42\n",
    "concurrency.my": "40\n30\n200\ntrue\nfalse\n150\n50\n31\n",
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
