"""Burn test: the checker goes on after a declaration's error, and nothing
follows from it (MYLA-110, D84).

For every mutant of `_mutants` (an example with one declaration broken), the
Python checker reports the injected error and nothing else, since the examples
have no errors of their own, and never raises anything but a Myla error. The
checker gate (test_selfhost_checker.py) compares the self-hosted checker on the
same mutants.
"""
import unittest

from myla.errors import MylaError
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check

from ._mutants import mutants


class DeclarationRecovery(unittest.TestCase):
    def test_mutants(self):
        cases = mutants()
        self.assertGreater(len(cases), 300)
        for name, src, first in cases:
            with self.subTest(mutant=name):
                with self.assertRaises(MylaError) as ctx:
                    check(parse(tokenize(src)))
                errs = [ctx.exception, *ctx.exception.more]
                self.assertEqual([e.message for e in errs], [first])


if __name__ == "__main__":
    unittest.main()
