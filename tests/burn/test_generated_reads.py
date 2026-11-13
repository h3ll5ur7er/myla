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


if __name__ == "__main__":
    unittest.main()
