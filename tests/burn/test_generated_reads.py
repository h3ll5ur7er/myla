"""Burn test: reads beside a mutation, generated (MYLA-555).

The review's generator (`_gen_reads.py`, R5b's `gen_rd.py`): 89 expressions
that read a value from a container and then, in a later operand, call a
`var self` method that replaces every container the value came from. The
value read first must be the old one, as the interpreter has it; natively a
read that isn't copied before the later operand frees what it points to
(MYLA-543's B2). Interpreted, native and `--checked` must print the same.
The generator is small, so the suite runs all of it.
"""
from __future__ import annotations

import tempfile
import unittest

from . import _gen_reads as gen
from . import _differential
from ._differential import THREE, check, driver, run_all
from ._native import CAN_BUILD_NATIVE, SKIP_REASON, write_program

# the forms that fail today, with the task that fixes them
KNOWN: dict[str, str] = {}


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class ReadsBesideAMutation(unittest.TestCase):
    def test_every_form(self):
        names, cases = gen.driver_cases()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, driver(gen.PRE, cases), "reads.my")
            results = run_all(path, len(names), THREE)
        check(self, names, results, KNOWN)


class AFailureNamesItsSample(unittest.TestCase):
    """A failing generated case says how to draw its run again (D262): the
    seed, or that every case ran."""

    def failure(self) -> str:
        with self.assertRaises(AssertionError) as caught:
            check(self, ["a", "b"], {"interpreted": ["1", "2"], "native": ["1", "3"]}, {})
        return str(caught.exception)

    def test_the_seed_of_a_sample(self):
        old = _differential.FULL, _differential.SEED
        try:
            _differential.FULL, _differential.SEED = False, 4711
            self.assertIn("MYLA_GENERATED_SEED=4711", self.failure())
            _differential.FULL = True
            self.assertIn("MYLA_GENERATED=full MYLA_GENERATED_SEED=4711", self.failure())
        finally:
            _differential.FULL, _differential.SEED = old


if __name__ == "__main__":
    unittest.main()
