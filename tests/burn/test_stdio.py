"""Burn tests for the freestanding I/O runtime (v0.5.4, D29).

The committed `examples/stdio` program imports `std.io`/`std.process`, so it is
linked against the bundled standard library and then run through both the
interpreter and the native compiler, which must agree on stdout, stderr, and the
process exit status (the parity guarantee, extended to the I/O runtime)."""
import os
import unittest

from ._native import (
    CAN_BUILD_NATIVE,
    SKIP_REASON,
    build_and_run_full,
    check_file,
    interpret_full,
    run_source_both,
)

EXAMPLE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                 "examples", "stdio", "main.my")
)

EXPECTED_OUT = "hello, myla\nno newline here; then a full line\n"
EXPECTED_ERR = "diagnostics go to stderr\nwarn: done\n"
EXPECTED_CODE = 0


class TestStdioExample(unittest.TestCase):
    def test_interpreter(self):
        out, err, code = interpret_full(check_file(EXAMPLE))
        self.assertEqual(out, EXPECTED_OUT)
        self.assertEqual(err, EXPECTED_ERR)
        self.assertEqual(code, EXPECTED_CODE)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_native_matches_interpreter(self):
        # Re-link for each backend (monomorphization mutates the program).
        interp = interpret_full(check_file(EXAMPLE))
        native = build_and_run_full(check_file(EXAMPLE))
        self.assertEqual(native, (EXPECTED_OUT, EXPECTED_ERR, EXPECTED_CODE))
        self.assertEqual(interp, native)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestStdioParity(unittest.TestCase):
    """Interpreter and native backend must agree on (stdout, stderr, exit) for a
    range of I/O-runtime programs."""

    def test_nonzero_exit_status(self):
        out, err, code = run_source_both(
            "from std.process import exit\n"
            "fun main() { exit(7) }\n"
        )
        self.assertEqual((out, err, code), ("", "", 7))

    def test_exit_truncates_to_low_byte(self):
        out, err, code = run_source_both(
            "from std.process import exit\n"
            "fun main() { exit(258) }\n"   # 258 & 0xFF == 2
        )
        self.assertEqual(code, 2)

    def test_exit_short_circuits_remaining_output(self):
        out, err, code = run_source_both(
            "from std.io import println\n"
            "from std.process import exit\n"
            "fun main() {\n"
            "    println(\"before\")\n"
            "    exit(0)\n"
            "    println(\"after\")\n"   # never reached
            "}\n"
        )
        self.assertEqual((out, err, code), ("before\n", "", 0))

    def test_raw_write_to_chosen_fd(self):
        out, err, code = run_source_both(
            "from std.io import write\n"
            "fun main() {\n"
            "    write(1, \"out-\")\n"
            "    write(2, \"err-\")\n"
            "    write(1, \"more\")\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("out-more", "err-", 0))

    def test_utf8_bytes_written_verbatim(self):
        out, err, code = run_source_both(
            "from std.io import println\n"
            "fun main() { println(\"héllo λ 😀\") }\n"
        )
        self.assertEqual((out, err, code), ("héllo λ 😀\n", "", 0))

    def test_args_round_trip(self):
        out, err, code = run_source_both(
            "from std.io import println\n"
            "from std.process import args\n"
            "fun main() {\n"
            "    for a in args() { println(a) }\n"
            "}\n",
            args=["alpha", "be ta", "λ"],
        )
        self.assertEqual((out, err, code), ("prog\nalpha\nbe ta\nλ\n", "", 0))

    def test_argc_via_len(self):
        out, _, _ = run_source_both(
            "from std.process import args\n"
            "fun main() { print(len(args())) }\n",
            args=["x", "y"],
        )
        self.assertEqual(out, "3\n")   # program name + 2 arguments

    def test_args_only_program_name(self):
        out, _, _ = run_source_both(
            "from std.process import args\n"
            "fun main() { print(len(args())) }\n",
        )
        self.assertEqual(out, "1\n")


# -- the committed args example, linked against the bundled stdlib -----------
ARGS_EXAMPLE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                 "examples", "args", "main.my")
)


class TestArgsExample(unittest.TestCase):
    EXPECTED_OUT = "4\nprog\none\ntwo\nthree\n"

    def test_interpreter(self):
        out, err, code = interpret_full(
            check_file(ARGS_EXAMPLE), argv=["prog", "one", "two", "three"])
        self.assertEqual(out, self.EXPECTED_OUT)
        self.assertEqual((err, code), ("", 0))

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_native_matches_interpreter(self):
        argv_tail = ["one", "two", "three"]
        interp = interpret_full(
            check_file(ARGS_EXAMPLE), argv=["prog", *argv_tail])
        native = build_and_run_full(
            check_file(ARGS_EXAMPLE), args=argv_tail, argv0="prog")
        self.assertEqual(native, (self.EXPECTED_OUT, "", 0))
        self.assertEqual(interp, native)


if __name__ == "__main__":
    unittest.main()
