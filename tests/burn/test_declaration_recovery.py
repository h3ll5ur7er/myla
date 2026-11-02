"""Burn test: the checker goes on after a declaration's error, and nothing
follows from it (MYLA-110, D84).

For every mutant of `_mutants` (an example with one declaration broken), the
Python checker reports the injected error and nothing else, since the examples
have no errors of their own, and never raises anything but a Myla error. Its
answers are recorded (`tests/burn/_golden.py`, MYLA-219). The checker gate
(test_selfhost_checker.py) compares the self-hosted checker on the same
mutants with the same answers.
"""
import unittest

from ._golden import golden
from ._mutants import mutants


@golden("declaration_recovery.messages")
def _messages(src: str) -> list[str] | None:
    """The messages of the errors the Python checker reports for `src`, or
    None if it accepts it."""
    from myla.errors import MylaError
    from myla.lexer import tokenize
    from myla.parser import parse
    from myla.types import check
    try:
        check(parse(tokenize(src)))
    except MylaError as exc:
        return [e.message for e in [exc, *exc.more]]
    return None


class DeclarationRecovery(unittest.TestCase):
    def test_mutants(self):
        cases = mutants()
        self.assertGreater(len(cases), 300)
        for name, src, first in cases:
            with self.subTest(mutant=name):
                messages = _messages(src)
                self.assertIsNotNone(messages, "the checker accepts the mutant")
                self.assertEqual(messages, [first])


if __name__ == "__main__":
    unittest.main()
