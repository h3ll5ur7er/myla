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
    run_file_both_now,
    run_source_both_now,
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
    "    for b in bytes { sb.append_byte(b) }\n"
    "    return sb.build()\n"
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
    "        _ => \"other\",\n"
    "    }\n"
    "}\n"
)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestSubprocessExample(unittest.TestCase):
    # The example names SpawnError's causes (D129): its own expectation, not
    # the retired toolchain's recorded answer.
    def test_interpreter_and_native(self):
        self.assertEqual(run_file_both_now(EXAMPLE), (EXPECTED_OUT, EXPECTED_ERR, EXPECTED_CODE))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestSubprocessParity(unittest.TestCase):
    """Interpreter and native backend must agree on (stdout, stderr, exit) when
    spawning subprocesses and capturing their output."""

    def test_captures_stdout(self):
        out, err, code = run_source_both_now(
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
        out, err, code = run_source_both_now(
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
        out, err, code = run_source_both_now(
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
        out, err, code = run_source_both_now(
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
        out, err, code = run_source_both_now(
            PRELUDE +
            "fun main() {\n"
            "    match command(\"/bin/echo\").arg(\"a\").args([\"b\", \"c\"]).output() {\n"
            "        Ok(o) => write(1, decode(o.stdout)),\n"
            "        Err(e) => println(err_str(e)),\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("a b c\n", "", 0))

    def test_a_child_gets_sigpipe_back(self):
        # the runtime ignores SIGPIPE (D146), which an exec would keep: a
        # child's `yes` would report its broken pipe on stderr instead of
        # stopping as it does anywhere
        out, err, code = run_source_both_now(
            "from std.process import run\n\n"
            "fun main() {\n"
            "    match run(\"/bin/sh\", [\"-c\", \"yes | head -1\"]) {\n"
            "        Ok(o) => { print(f\"stdout {o.stdout.len()} bytes, stderr {o.stderr.len()} bytes\") },\n"
            "        Err(e) => { print(\"failed\") },\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("stdout 2 bytes, stderr 0 bytes\n", "", 0))
