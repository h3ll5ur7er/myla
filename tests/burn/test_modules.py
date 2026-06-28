"""Burn tests for the module system (v0.5.1): a committed multi-file example is
linked, type-checked, and run through both the interpreter and the native
compiler, which must agree (the core parity guarantee, extended to modules)."""
import os
import unittest

from myla.loader import link
from myla.types import check

from ._native import (
    CAN_BUILD_NATIVE,
    SKIP_REASON,
    build_and_run_checker,
    interpret_checker,
)

MODULES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                 "examples", "modules")
)

EXPECTED = "7\ndone!\n7\n"


def _check_entry(entry: str):
    return check(link(os.path.join(MODULES_DIR, entry)))


class TestModuleExample(unittest.TestCase):
    def test_interpreter(self):
        self.assertEqual(interpret_checker(_check_entry("main.my")), EXPECTED)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_native_matches_interpreter(self):
        checker = _check_entry("main.my")
        # Re-link for the native build (monomorphization mutates the program).
        native_out, code = build_and_run_checker(_check_entry("main.my"))
        self.assertEqual(code, 0)
        self.assertEqual(native_out, EXPECTED)
        self.assertEqual(interpret_checker(checker), native_out)


if __name__ == "__main__":
    unittest.main()
