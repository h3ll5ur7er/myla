"""Burn test: the negative corpus in ``examples/errors/`` is rejected as expected.

Project convention (see README "Regression corpus"): every language feature is
exercised by a runnable example, and every *known edge case, past bug, and error*
is pinned by a program the toolchain must reject. The files in
``examples/errors/`` are those rejections.

Each file declares the diagnostic it expects with a directive comment on its own
line::

    //~ type error: cannot assign

The leading ``<lex|parse|type|runtime> error`` selects the pipeline stage that
must fail (lexer / parser / type-checker / interpreter), and the trailing text
is a substring the diagnostic message must contain. This catches two kinds of
regression at once: a feature that silently *stops* rejecting bad input, and one
that starts rejecting it for the *wrong* reason or in the wrong stage.
"""
import os
import re
import unittest

from myla.errors import LexError, MylaRuntimeError, ParseError, TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check

ERRORS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "examples", "errors")
)

_DIRECTIVE = re.compile(r"//~\s*(lex|parse|type|runtime)\s+error:\s*(.*?)\s*$")

# phase -> (exception class, how far to drive the pipeline)
_PHASES = {
    "lex": LexError,
    "parse": ParseError,
    "type": TypeCheckError,
    "runtime": MylaRuntimeError,
}


def _drive(phase: str, source: str) -> None:
    """Run the pipeline far enough to reach `phase`; let its error escape."""
    tokens = tokenize(source)
    if phase == "lex":
        return
    program = parse(tokens)
    if phase == "parse":
        return
    checker = check(program)
    if phase == "type":
        return
    Interpreter(checker).run()


def _corpus() -> list[str]:
    if not os.path.isdir(ERRORS_DIR):
        return []
    return sorted(f for f in os.listdir(ERRORS_DIR) if f.endswith(".my"))


def _directive(source: str) -> tuple[str, str]:
    matches = [m for line in source.splitlines() if (m := _DIRECTIVE.match(line.strip()))]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one '//~ <phase> error: <substr>' directive, "
            f"found {len(matches)}"
        )
    return matches[0].group(1), matches[0].group(2)


class TestErrorCorpus(unittest.TestCase):
    def test_corpus_is_not_empty(self):
        self.assertTrue(_corpus(), "no negative cases found in examples/errors/")


def _make(name: str):
    def test(self):
        with open(os.path.join(ERRORS_DIR, name), encoding="utf-8") as fh:
            source = fh.read()
        phase, needle = _directive(source)
        exc_type = _PHASES[phase]
        with self.assertRaises(exc_type, msg=f"{name}: expected a {phase} error") as ctx:
            _drive(phase, source)
        if needle:
            self.assertIn(
                needle.lower(),
                str(ctx.exception).lower(),
                f"{name}: diagnostic '{ctx.exception}' should contain '{needle}'",
            )
    return test


for _name in _corpus():
    setattr(TestErrorCorpus, f"test_{_name[:-3].replace('.', '_')}", _make(_name))


if __name__ == "__main__":
    unittest.main()
