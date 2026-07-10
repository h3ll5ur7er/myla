"""Burn tests for the subprocess runtime (std.process.run / Command, D29).

The committed `examples/subprocess` program imports `std.io`/`std.process`, so
it is linked against the bundled standard library and run through both the
interpreter and the native compiler, which must agree on stdout, stderr, and the
process exit status. The additional parity cases spawn small, universally
present helpers (`/bin/echo`, `/bin/sh`) and assert both backends observe the
same captured output, exit code, and signal.
"""
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
                 "examples", "subprocess", "main.my")
)

EXPECTED_OUT = (
    "hello from myla\n"
    "exited 0\n"
    "built with Command\n"
    "exited 0\n"
    "not found (as expected)\n"
)
EXPECTED_ERR = ""
EXPECTED_CODE = 0

# A `decode`/`status_str` prelude shared by the parity programs below: turn a
# captured `[uint8]` buffer into a `str` and render an `ExitStatus`.
PRELUDE = (
    "from std.io import write, println\n"
    "from std.process import run, command, Output, ExitStatus, SpawnError\n"
    "fun decode(bytes: [uint8]) -> str {\n"
    "    var sb = StringBuilder()\n"
    "    for b in bytes { append_byte(sb, b) }\n"
    "    return build(sb)\n"
    "}\n"
    "fun status_str(s: ExitStatus) -> str {\n"
    "    return match s {\n"
    "        ExitStatus.Exited(c) => format(\"exit {}\", c),\n"
    "        ExitStatus.Signaled(g) => format(\"signal {}\", g),\n"
    "    }\n"
    "}\n"
    "fun err_str(e: SpawnError) -> str {\n"
    "    return match e {\n"
    "        SpawnError.NotFound => \"notfound\",\n"
    "        SpawnError.PermissionDenied => \"perm\",\n"
    "        SpawnError.Other(code) => \"other\",\n"
    "    }\n"
    "}\n"
)


class TestSubprocessExample(unittest.TestCase):
    def test_interpreter(self):
        out, err, code = interpret_full(check_file(EXAMPLE))
        self.assertEqual(out, EXPECTED_OUT)
        self.assertEqual(err, EXPECTED_ERR)
        self.assertEqual(code, EXPECTED_CODE)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_native_matches_interpreter(self):
        interp = interpret_full(check_file(EXAMPLE))
        native = build_and_run_full(check_file(EXAMPLE))
        self.assertEqual(native, (EXPECTED_OUT, EXPECTED_ERR, EXPECTED_CODE))
        self.assertEqual(interp, native)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestSubprocessParity(unittest.TestCase):
    """Interpreter and native backend must agree on (stdout, stderr, exit) when
    spawning subprocesses and capturing their output."""

    def test_captures_stdout(self):
        out, err, code = run_source_both(
            PRELUDE +
            "fun main() {\n"
            "    match run(\"/bin/echo\", [\"hi\", \"there\"]) {\n"
            "        Ok(o) => write(1, decode(o.stdout)),\n"
            "        Err(e) => println(err_str(e)),\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("hi there\n", "", 0))

    def test_captures_stderr_and_exit_code(self):
        out, err, code = run_source_both(
            PRELUDE +
            "fun main() {\n"
            "    match run(\"/bin/sh\", [\"-c\", \"printf out; printf err 1>&2; exit 5\"]) {\n"
            "        Ok(o) => {\n"
            "            write(1, decode(o.stdout))\n"
            "            write(2, decode(o.stderr))\n"
            "            println(status_str(o.status))\n"
            "        }\n"
            "        Err(e) => println(err_str(e)),\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("outexit 5\n", "err", 0))

    def test_reports_terminating_signal(self):
        out, err, code = run_source_both(
            PRELUDE +
            "fun main() {\n"
            "    match run(\"/bin/sh\", [\"-c\", \"kill -9 $$\"]) {\n"
            "        Ok(o) => println(status_str(o.status)),\n"
            "        Err(e) => println(err_str(e)),\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("signal 9\n", "", 0))

    def test_missing_program_is_not_found(self):
        out, err, code = run_source_both(
            PRELUDE +
            "fun main() {\n"
            "    match run(\"/no/such/program\", []) {\n"
            "        Ok(o) => println(\"unexpected\"),\n"
            "        Err(e) => println(err_str(e)),\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("notfound\n", "", 0))

    def test_command_builder_matches_run(self):
        out, err, code = run_source_both(
            PRELUDE +
            "fun main() {\n"
            "    match command(\"/bin/echo\").arg(\"a\").args([\"b\", \"c\"]).output() {\n"
            "        Ok(o) => write(1, decode(o.stdout)),\n"
            "        Err(e) => println(err_str(e)),\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("a b c\n", "", 0))
