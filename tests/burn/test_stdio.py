"""Burn tests for the freestanding I/O runtime (v0.5.4, D29).

The committed `examples/stdio` program imports `std.io`/`std.process`, so it is
linked against the bundled standard library and then run through both the
interpreter and the native compiler, which must agree on stdout, stderr, and the
process exit status (the parity guarantee, extended to the I/O runtime)."""
import os
import signal
import subprocess
import tempfile
import time
import unittest

from ._native import (
    CAN_BUILD_NATIVE,
    SKIP_REASON,
    TEST_TARGET,
    Program,
    build_and_run_full,
    check_file,
    interpret_full,
    native_build,
    run_argv,
    run_source_both,
    write_program,
)
from ._tools import STDLIB_ROOT, selfhost_tool

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
            "fun main() { print(args().len()) }\n",
            args=["x", "y"],
        )
        self.assertEqual(out, "3\n")   # program name + 2 arguments

    def test_args_only_program_name(self):
        out, _, _ = run_source_both(
            "from std.process import args\n"
            "fun main() { print(args().len()) }\n",
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



# D146: a program printing without end into a pipe whose reader has gone ends
# quietly, as Unix tools do in `yes | head`; a write to another descriptor
# reports the error instead (`BrokenPipe`), as the runtime ignores SIGPIPE.
PRINTS_FOREVER = """fun main() {
    var i = 0
    while true {
        print(f"line {i}")
        i += 1
    }
}
"""

WRITES_TO_FD_3 = """from std.io import write
from std.fs import IoError

fun main() {
    match write(3, "to a pipe nobody reads\\n") {
        Ok(u) => { print("written") },
        Err(e) => {
            match e {
                IoError.BrokenPipe => { print("broken pipe") },
                _ => { print("another error") },
            }
        },
    }
    print("still running")
}
"""


# D153: a write without a result that the system refuses (a full disk:
# /dev/full) ends the program with a runtime error and status 1, where the
# output used to be lost without a word (the review of 2026-11-06, R8)
WRITES_TO_A_FULL_DISK = """from std.io import println, eprintln

fun main() {
    print("one")
    println("two")
    eprintln("to stderr")
}
"""


def _argvs(tmp: str, source: str) -> list[tuple[str, list[str], str | None]]:
    """The interpreter's and the native binary's command lines for `source`."""
    path = write_program(tmp, source)
    binary = os.path.join(tmp, "prog")
    native_build(Program(path), binary)
    argv, exe = run_argv(binary, binary)
    return [("interpreter", [selfhost_tool("main"), "run", path, "--stdlib", STDLIB_ROOT], None),
            ("native", argv, exe)]


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class BrokenPipe(unittest.TestCase):
    def test_printing_into_a_closed_pipe_ends_quietly(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, argv, exe in _argvs(tmp, PRINTS_FOREVER):
                with self.subTest(run=name):
                    p = subprocess.Popen(argv, executable=exe, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    first = p.stdout.readline()
                    p.stdout.close()
                    err = p.stderr.read()
                    code = p.wait(timeout=60)
                    p.stderr.close()
                    self.assertEqual(first, b"line 0\n")
                    self.assertEqual(err, b"")
                    # SIGPIPE natively; 141, the code a shell shows for it, on
                    # a target without signals
                    self.assertIn(code, (-signal.SIGPIPE, 141))

    def test_a_write_to_another_descriptor_reports_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, argv, exe in _argvs(tmp, WRITES_TO_FD_3):
                with self.subTest(run=name):
                    r, w = os.pipe()
                    os.close(r)
                    os.dup2(w, 3)
                    os.close(w)
                    try:
                        p = subprocess.run(argv, executable=exe, pass_fds=(3,), capture_output=True, text=True, timeout=60)
                    finally:
                        os.close(3)
                    self.assertEqual((p.stdout, p.stderr, p.returncode), ("broken pipe\nstill running\n", "", 0))


    def test_a_write_to_a_full_disk_ends_with_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, argv, exe in _argvs(tmp, WRITES_TO_A_FULL_DISK):
                with self.subTest(run=name, stream="stdout"):
                    with open("/dev/full", "w") as full:
                        p = subprocess.run(argv, executable=exe, stdout=full, stderr=subprocess.PIPE, text=True, timeout=60)
                    self.assertEqual((p.stderr, p.returncode),
                                     ("runtime error: write failed: no space left on device\n", 1))
                with self.subTest(run=name, stream="println"):
                    src = WRITES_TO_A_FULL_DISK.replace('    print("one")\n', "")
                    path = write_program(tmp, src, f"{name}2.my")
                    cmd = argv
                    if name == "native":
                        binary = os.path.join(tmp, "prog2")
                        native_build(Program(path), binary)
                        cmd, exe2 = run_argv(binary, binary)
                    else:
                        cmd, exe2 = [selfhost_tool("main"), "run", path, "--stdlib", STDLIB_ROOT], None
                    with open("/dev/full", "w") as full:
                        p = subprocess.run(cmd, executable=exe2, stdout=full, stderr=subprocess.PIPE, text=True, timeout=60)
                    self.assertEqual((p.stderr, p.returncode),
                                     ("runtime error: write failed: no space left on device\n", 1))
                with self.subTest(run=name, stream="stderr"):
                    with open("/dev/full", "w") as full:
                        p = subprocess.run(argv, executable=exe, stdout=subprocess.PIPE, stderr=full, text=True, timeout=60)
                    # the message itself can't be written either: the status says it
                    self.assertEqual((p.stdout, p.returncode), ("one\ntwo\n", 1))


# MYLA-457: a write to a full non-blocking output waits for room (a poll)
# instead of trying again at once: 2 MiB through `print`, `println` and an
# `FdStream`, and through `write_async` in a task, into a non-blocking pipe
# read 64 KiB every 20 ms. The writer spun on EAGAIN: 0.29 s of CPU over
# 0.34 s; a blocking pipe's writer takes about 0.01 s.
SYNC_WRITER = """from std.io import println, fd_stream

fun main() {
    let line = "x".repeat(1023)
    for i in 0..512 {
        print(line)
    }
    for i in 0..512 {
        println(line)
    }
    var out = fd_stream(1)
    let b = (line + "\\n").bytes()
    for i in 0..1024 {
        match out.write(b) {
            Ok(n) => {}
            Err(e) => { panic(f"{e}") }
        }
    }
}
"""

ASYNC_WRITER = """import std.io as io
import std.task as task

async fun ticks() -> int {
    var n = 0
    for i in 0..10 {
        await task.sleep(20)
        n += 1
    }
    return n
}

#main
async fun main() {
    let b = ("x".repeat(1023) + "\\n").bytes()
    var out = io.fd_stream(1)
    async let t = ticks()
    for i in 0..2048 {
        match await out.write_async(b) {
            Ok(n) => {}
            Err(e) => { panic(f"{e}") }
        }
    }
    let n = await t
}
"""


def _drained_slowly(argv: list[str], exe: str | None) -> tuple[int, bytes, int, float, float]:
    """`argv` run with its standard output a non-blocking pipe read 64 KiB
    every 20 ms: the bytes read, its stderr, its exit code, its CPU time and
    the wall time, in seconds."""
    r, w = os.pipe()
    os.set_blocking(w, False)
    t0 = time.monotonic()
    p = subprocess.Popen(argv, executable=exe, stdout=w, stderr=subprocess.PIPE)
    os.close(w)
    got = 0
    with os.fdopen(r, "rb", buffering=0) as reader:
        while chunk := reader.read(65536):
            got += len(chunk)
            time.sleep(0.02)
    err = p.stderr.read()
    p.stderr.close()
    _, status, usage = os.wait4(p.pid, 0)
    wall = time.monotonic() - t0
    p.returncode = os.waitstatus_to_exitcode(status)
    return got, err, p.returncode, usage.ru_utime + usage.ru_stime, wall


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class NonBlockingOutput(unittest.TestCase):
    def test_a_full_output_is_waited_for_not_spun_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kind, source in [("sync", SYNC_WRITER), ("async", ASYNC_WRITER)]:
                os.makedirs(os.path.join(tmp, kind))
                for name, argv, exe in _argvs(os.path.join(tmp, kind), source):
                    with self.subTest(writes=kind, run=name):
                        got, err, code, cpu, wall = _drained_slowly(argv, exe)
                        self.assertEqual((got, err, code), (2048 * 1024, b"", 0))
                        # the reader alone takes 0.64 s; the interpreter's
                        # start (reading the library) is most of what is left
                        self.assertGreater(wall, 0.6)
                        self.assertLess(cpu, 0.4 * wall, f"{cpu:.2f} s of CPU in {wall:.2f} s")


# MYLA-572: a read of two billion bytes of a short input, and how much the
# peak of the process's address space grew meanwhile, in kB (-1 without
# /proc/self/status)
READS_A_HUGE_COUNT = """import std.io as io
import std.fs as fs
import std.num as num
from std.io import Read

fun peak_kb() -> int {
    return match fs.read_to_string("/proc/self/status") {
        Ok(s) => {
            var kb = -1
            for l in s.lines() {
                if l.starts_with("VmPeak:") {
                    kb = num.parse_int(l[7:].trim().split(" ")[0]).unwrap_or(-1) as int
                }
            }
            kb
        }
        Err(e) => -1
    }
}

fun main() {
    let before = peak_kb()
    var r = io.fd_stream(0)
    match r.read(2000000000) {
        Ok(b) => print(f"{b.len()} bytes")
        Err(e) => print(f"error {e}")
    }
    let after = peak_kb()
    print(if before < 0 || after < 0 { -1 } else { after - before })
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class HugeReads(unittest.TestCase):
    def test_a_huge_count_costs_the_room_of_a_few_mib(self):
        """MYLA-572: `read(n)` may give fewer bytes than asked (D177), so its
        room is capped (4 MiB): a read of 2,000,000,000 bytes of `abc` used
        to ask for 2 GB first, `out of memory` under a 400 MB limit. The
        program reports its own address space's growth; on wasm32 /proc is
        Node's, and the linear memory's peak is the measure."""
        with tempfile.TemporaryDirectory() as tmp:
            for name, argv, exe in _argvs(tmp, READS_A_HUGE_COUNT):
                with self.subTest(run=name):
                    mem = os.path.join(tmp, "memory")
                    env = dict(os.environ, MYLA_WASM_MEMORY_OUT=mem)
                    p = subprocess.run(argv, executable=exe, input="abc\n", capture_output=True, text=True,
                                       env=env, timeout=120)
                    self.assertEqual((p.stderr, p.returncode), ("", 0))
                    got, grown = p.stdout.split("\n")[:2]
                    self.assertEqual(got, "4 bytes")
                    if name == "native" and TEST_TARGET == "wasm32-wasi":
                        with open(mem, encoding="utf-8") as fh:
                            self.assertLess(int(fh.read()), 64 << 20)
                    else:
                        self.assertLess(int(grown), 65536, f"{grown} kB more address space")


if __name__ == "__main__":
    unittest.main()
