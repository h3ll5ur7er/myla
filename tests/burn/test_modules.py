"""Burn tests for the module system (v0.5.1): a committed multi-file example is
linked, type-checked, and run through both the interpreter and the native
compiler, which must agree (the core parity guarantee, extended to modules).

The interpreter is the self-hosted one (`myla run`); the native output is also
compared with the retired Python interpreter's recorded answer (MYLA-219)."""
import os
import tempfile
import unittest

from ._native import (
    CAN_BUILD_NATIVE,
    SKIP_REASON,
    build_and_run_checker,
    check_file,
    interpret_checker,
    run_file_both_now,
    selfhost_run,
    write_program,
)

MODULES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                 "examples", "modules")
)

EXPECTED = "7\ndone!\n7\n"


def _check_entry(entry: str):
    return check_file(os.path.join(MODULES_DIR, entry))


class TestModuleExample(unittest.TestCase):
    def test_interpreter(self):
        out, err, code = selfhost_run(os.path.join(MODULES_DIR, "main.my"))
        self.assertEqual((err, code), ("", 0))
        self.assertEqual(out, EXPECTED)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_native_matches_interpreter(self):
        program = _check_entry("main.my")
        native_out, code = build_and_run_checker(program)
        self.assertEqual(code, 0)
        self.assertEqual(native_out, EXPECTED)
        self.assertEqual(interpret_checker(program), native_out)


# Two modules, each deriving `Eq` for a type declared at the same line and
# column: each keeps its `Eq` (MYLA-364; the checker told derived types
# apart by their position, so one of them lost it).
SAME_PLACE_DUP = (
    "// the same line as main.my's derive\n"
    "#derive(Eq)\npub enum E { A, B }\n"
    "pub fun is_a(e: E) -> bool { return e == E.A }\n"
)
SAME_PLACE_MAIN = (
    "import .dup as dup\n"
    "#derive(Eq)\npub enum E { A, B }\n"
    "pub fun is_a(e: E) -> bool { return e == E.A }\n"
    "fun main() {\n    print(is_a(E.B))\n    print(dup.is_a(dup.E.A))\n}\n"
)


class TestDerivesAtTheSamePlace(unittest.TestCase):
    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_both_keep_their_eq(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_program(tmp, SAME_PLACE_DUP, "dup.my")
            path = write_program(tmp, SAME_PLACE_MAIN)
            self.assertEqual(run_file_both_now(path), ("false\ntrue\n", "", 0))


if __name__ == "__main__":
    unittest.main()
