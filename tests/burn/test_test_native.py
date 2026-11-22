"""Burn test: `myla test --native` and `--target` (D162, MYLA-307).

`myla test --native` builds a harness program from a file and its cases
(selfhost/harness.my) and runs it: the report is the interpreter's, line
for line, on every example and standard library module with cases (but the
runtime itself, which doesn't build as a program), failing reports and what
the cases write on stderr included (MYLA-418). What differs natively by
design: a failed case runs no deferred block (its child process ends). An
expected `[panic]` matches exactly on both (D183); until native runtime
errors carry the interpreter's texts (MYLA-415), one such as an index error
can't be expected on both. For another target the harness runs under the emulator
`--target` implies (qemu-aarch64) or MYLA_EMULATOR names (Node for wasm32,
where the harness can start no child process: `myla test` runs it, and again
after each case that ended a run, MYLA-370)."""
import glob
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, HOST_TARGET, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool
from tests.burn.test_test_functions import _ASYNC, _ASYNC_WANT, _FUNCTIONS, _FUNCTIONS_WANT, _UNWINDING, _myla, _write

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_RUN_MJS = os.path.join(_REPO, "tools", "wasm", "run.mjs")


def _tool(args: list[str], cwd: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """`myla` as `_myla` runs it, but with the standard library root as
    `env` (MYLA_STDLIB) gives it, else the one the tools carry."""
    full = {k: v for k, v in os.environ.items() if k != "MYLA_STDLIB"}
    full.update(env or {})
    return subprocess.run([selfhost_tool("main"), *args], capture_output=True, text=True, cwd=cwd, env=full)


def _case_count(path: str) -> int:
    """The `#test` attributes of a file, one case each."""
    with open(path, encoding="utf-8") as fh:
        return sum(1 for line in fh if line.lstrip().startswith("#test"))

# natively a failed case runs no deferred block, so nothing is printed by
# them and a deferred block's own failure isn't seen; a deferred block that
# fails on a normal return is the runtime error it raises
_UNWINDING_NATIVE_WANT = """FAIL  unwinds_nested_blocks: runtime error: boom
FAIL  unwinds_on_exit: exited with status 2
FAIL  reports_a_failing_defer: runtime error: boom
PASS  passes_and_cleans
FAIL  fails_with_an_io_error: not found (NotFound)
FAIL  fails_and_cleans: runtime error: after writing
FAIL  a_passing_defer_failure_fails: runtime error: late
PASS  output_of_a_pass_is_hidden

2/8 passed.
"""

# the async cases: the same but for the deferred blocks of the failed cases
_ASYNC_NATIVE_WANT = _ASYNC_WANT.replace("      | case's defer\n", "").replace("      | async defer ran\n", "")

# MYLA-357: a receiver of every kind with an empty value, and a literal one
# of another integer type, bound with the argument's type; a method on a
# built-in type named by its type. MYLA-361: a uint64 of 2^63 or more shown
# unsigned, alone and inside a struct, a tuple, a list and an enum
_RECEIVERS = """#derive(Eq)
struct H { s: uint64 }

impl [str] {
    #test([], "-")[1]
    #test(["a"], "-")[2]
    fun width_with(self, sep: str) -> int {
        return self.len() + sep.len()
    }
}

impl [str: int] {
    #test([:])[0]
    #test(["a": 2])[2]
    fun sum_values(self) -> int {
        var t = 0
        for k in self.keys() {
            t += self[k]
        }
        return t
    }
}

impl str {
    #test("")[0]
    fun byte_count(self) -> int {
        return self.len()
    }
}

impl int8 {
    #test(5, 2)[7]
    fun plus_i8(self, d: int8) -> int8 {
        return self + d
    }
}

#test()[1u64]
fun big() -> uint64 {
    return 0xFFFFFFFFFFFFFFFF
}

#test()[H { s: 1 }]
fun big_h() -> H {
    return H { s: 0xFFFFFFFFFFFFFFFF }
}

#test()[(1u64, 2)]
fun big_pair() -> (uint64, int) {
    return (0xFFFFFFFFFFFFFFFF, 2)
}

#test()[[1u64]]
fun big_list() -> [uint64] {
    return [0x8000000000000000]
}

#test()[Some(1u64)]
fun big_some() -> Option<uint64> {
    return Some(0x8000000000000000)
}

#test()[panic("no")]
fun big_returns() -> uint64 {
    return 0x8000000000000000
}
"""

_RECEIVERS_WANT = """PASS  [str].width_with #1
PASS  [str].width_with #2
PASS  [str: int32].sum_values #1
PASS  [str: int32].sum_values #2
PASS  str.byte_count #1
PASS  int8.plus_i8 #1
FAIL  big #1: expected 1, got 18446744073709551615
FAIL  big_h #1: expected H { s: 1 }, got H { s: 18446744073709551615 }
FAIL  big_pair #1: expected (1, 2), got (18446744073709551615, 2)
FAIL  big_list #1: expected [1], got [9223372036854775808]
FAIL  big_some #1: expected Option.Some(1), got Option.Some(9223372036854775808)
FAIL  big_returns #1: expected runtime error 'no', got 9223372036854775808

6/12 passed.
"""

# MYLA-418: failing reports, held to both runners (the review of 2026-11-09,
# M6 to M9): a float in the interpreter's form (`2.0`, `1e+16`), an `exit(0)`
# in a case, which is no pass, and `[exit(0)]`, which is; a test function's
# scalar `Err`; an expected panic matched exactly (D183); and what a case
# writes on stderr, passed on and never taken for a verdict or a runtime
# error, a partial line before a panic too
_FAILING = """from std.io import eprint, write
from std.process import exit

#test()[7.25]
fun two() -> float {
    return 2.0
}

#test()[7.25]
fun big() -> float {
    return 1e16
}

#test()[1.5f32]
fun tenth() -> float32 {
    return 0.1f32
}

#test()[[1.0]]
fun floats() -> [float] {
    return [2.0, -0.0]
}

#test(0)[1]
#test(0)[exit(0)]
#test(3)[exit(0)]
#test(4)[panic("boom")]
fun leaves(n: int) -> int {
    exit(n)
    return 2
}

#test
fun exits_early() {
    exit(0)
    assert(1 == 2, "not reached")
}

#test
fun big_err() -> Result<(), uint64> {
    return Err(0xFFFFFFFFFFFFFFFF)
}

#test
fun float_err() -> Result<(), float> {
    return Err(2.5)
}

#test
fun char_err() -> Result<(), char> {
    return Err('x')
}

#test
fun bool_err() -> Result<(), bool> {
    return Err(false)
}

#test("bo")[panic("boom")]
#test("x")[panic("")]
#test("boom")[panic("boom")]
#test("boom")[panic("boomer")]
#test("boom")[exit(1)]
fun boom(m: str) -> int {
    panic(m)
}

#test()[1]
fun logs_a_verdict() -> int {
    eprint("myla test: fake verdict\\n")
    return 1
}

#test()[1]
fun logs_an_error() -> int {
    eprint("runtime error: fake\\n")
    return 1
}

#test()[panic("boom")]
fun partial_line_then_panic() -> int {
    let e = write(2, "progress... ")
    panic("boom")
}

#test()[2]
fun logs_and_fails() -> int {
    eprint("to stderr\\n")
    print("to stdout")
    return 1
}
"""

_FAILING_WANT = """FAIL  two #1: expected 7.25, got 2.0
FAIL  big #1: expected 7.25, got 1e+16
FAIL  tenth #1: expected 1.5, got 0.10000000149011612
FAIL  floats #1: expected [1.0], got [2.0, -0.0]
FAIL  leaves #1: exited with status 0
PASS  leaves #2
FAIL  leaves #3: expected exit status 0, exited with status 3
FAIL  leaves #4: expected runtime error 'boom', exited with status 4
FAIL  exits_early: exited with status 0
FAIL  big_err: 18446744073709551615
FAIL  float_err: 2.5
FAIL  char_err: x
FAIL  bool_err: false
FAIL  boom #1: expected runtime error 'boom', got runtime error 'bo'
FAIL  boom #2: expected runtime error '', got runtime error 'x'
PASS  boom #3
FAIL  boom #4: expected runtime error 'boomer', got runtime error 'boom'
FAIL  boom #5: expected exit status 1, got runtime error 'boom'
PASS  logs_a_verdict #1
PASS  logs_an_error #1
PASS  partial_line_then_panic #1
FAIL  logs_and_fails #1: expected 2, got 1
      | to stdout

5/22 passed.
"""

_FAILING_STDERR = "myla test: fake verdict\nruntime error: fake\nprogress... to stderr\n"

# an expected runtime error of the runtime's own, matched exactly on both
# runners (D183): needs native runtime errors with the interpreter's texts
# (MYLA-415)
_RUNTIME_TEXTS = """#test([1, 2], 5)[panic("list index 5 out of bounds (len 2)")]
#test([1, 2], 1)[panic("list index 5 out of bounds (len 2)")]
fun at(xs: [int], i: int) -> int {
    return xs[i]
}

#test(["a": 1], "b")[panic("map key 'b' not found")]
fun value(m: [str: int], k: str) -> int {
    return m[k]
}
"""

_RUNTIME_TEXTS_WANT = """PASS  at #1
FAIL  at #2: expected runtime error 'list index 5 out of bounds (len 2)', got 2
PASS  value #1

2/3 passed.
"""

# a test function's `Err` of a list or tuple, shown alike (M8; the
# interpreter's half is MYLA-414's)
_COMPOUND_ERR = """#test
fun list_err() -> Result<(), [int]> {
    return Err([1])
}

#test
fun pair_err() -> Result<(), (int, str)> {
    return Err((1, "a"))
}
"""

# MYLA-547 (D191): how a case ended, told by a framed record the runtime
# writes: a message of many lines matched whole (C5), the old protocol's
# marks and a line like a runtime error's written by a case and then an
# `exit`, which is reported as the exit it is, an exit status as the process
# ends with it and an expected one outside 0 to 255 refused (C7), an empty
# `Err`, which fails (C6), an `Err` of `()` and of a closure shown alike, an
# empty stdin for every case, a deferred block that fails as the case
# returns (M12), values with no form of their own inside an `Err`, the
# arguments a case sees (the program only), and a stack overflow, held to
# every runner
_FRAMED = """from std.io import eprint, write, stdin
from std.process import exit, args

#test("a\\nruntime error: b")[panic("a\\nruntime error: b")]
#test("a\\nruntime error: b")[panic("b")]
fun boom(m: str) -> int {
    panic(m)
}

#test
fun wraps_a_tools_error() {
    panic("the tool failed:\\nruntime error: list index 3 out of bounds (len 3)\\n  --> t.my:1:1")
}

#test
fun old_marks_then_exit() {
    eprint("\\u{1}myla-done\\u{1}")
    exit(3)
}

#test
fun a_runtime_error_line_then_exit() {
    eprint("runtime error: fake\\n")
    exit(1)
}

#test
fun case_marks_then_fail() {
    let w = write(1, "\\u{1}myla-case\\u{1}")
    eprint("\\u{1}myla-case\\u{1}")
    panic("x")
}

#test
fun after_the_marks() {}

#test(256)[exit(0)]
#test(256)[exit(256)]
#test(-1)[exit(255)]
fun leaves(n: int) -> int {
    exit(n)
    return 2
}

#test
fun empty_err() -> Result<(), str> {
    return Err("")
}

#test
fun unit_err() -> Result<(), ()> {
    return Err(())
}

#test
fun function_err() -> Result<(), (int) -> int> {
    return Err((x: int) => x + 1)
}

#test
fun reads_stdin() {
    var input = stdin()
    match input.read_line() {
        Ok(None) => {},
        Ok(Some(line)) => { panic(f"read a line: {line}") },
        Err(e) => { panic("an error") },
    }
}

#test
async fun reads_stdin_async() {
    var input = stdin()
    match await input.read_line_async() {
        Ok(None) => {},
        Ok(Some(line)) => { panic(f"read a line: {line}") },
        Err(e) => { panic("an error") },
    }
}

#test(2)[panic("in defer")]
#test(3)[exit(5)]
#test(4)[4]
fun fails_in_defer(n: int) -> int {
    defer {
        if n == 2 { panic("in defer") }
        if n == 3 { exit(5) }
    }
    return n
}

#test
fun builders_err() -> Result<(), [StringBuilder]> {
    return Err([StringBuilder()])
}

#test
fun functions_err() -> Result<(), [(int) -> int]> {
    return Err([(x: int) => x + 1])
}

#test()[1]
fun its_arguments() -> int {
    return args().len()
}

#test(0)[panic("stack overflow")]
fun deep(n: int) -> int {
    return deep(n + 1) + 1
}
"""

_FRAMED_WANT = """PASS  boom #1
FAIL  boom #2: expected runtime error 'b', got runtime error 'a\\nruntime error: b'
FAIL  wraps_a_tools_error: runtime error: the tool failed:\\nruntime error: list index 3 out of bounds (len 3)\\n  --> t.my:1:1
FAIL  old_marks_then_exit: exited with status 3
FAIL  a_runtime_error_line_then_exit: exited with status 1
FAIL  case_marks_then_fail: runtime error: x
      | \x01myla-case\x01
PASS  after_the_marks
PASS  leaves #1
FAIL  leaves #2: expected exit status 256: a status is 0 to 255
PASS  leaves #3
FAIL  empty_err
FAIL  unit_err: ()
FAIL  function_err: <function>
PASS  reads_stdin
PASS  reads_stdin_async
PASS  fails_in_defer #1
PASS  fails_in_defer #2
PASS  fails_in_defer #3
FAIL  builders_err: [<StringBuilder>]
FAIL  functions_err: [<function>]
PASS  its_arguments #1
PASS  deep #1

11/22 passed.
"""

_FRAMED_STDERR = "\x01myla-done\x01runtime error: fake\n\x01myla-case\x01"

# M2 (MYLA-792): a case whose tasks write on stderr all the time while it
# fails; natively on four workers their writes cut the record, written in
# three writes, and 0 to 1 of the 4 cases passed
_NOISY = """import std.task as task
from std.io import eprint

async fun noisy(k: int) -> int {
    var i = 0
    while true {
        eprint("z")
        i += 1
        if i % 50 == 0 { await task.yield() }
    }
    return k
}

#test(1)[panic("boom: the message of the panic")]
#test(2)[panic("boom: the message of the panic")]
#test(3)[panic("boom: the message of the panic")]
#test(4)[panic("boom: the message of the panic")]
async fun noisy_tasks(n: int) -> int {
    async let a = noisy(1)
    async let b = noisy(2)
    async let c = noisy(3)
    await task.sleep(20)
    panic("boom: the message of the panic")
}
"""

_NOISY_WANT = "".join(f"PASS  noisy_tasks #{k}\n" for k in range(1, 5)) + "\n4/4 passed.\n"

# M2: a case that reads the run's nonce, writes a record of its own that
# says it passed, and has itself killed: it passed natively
_FORGED = """import std.process as process
import std.fs as fs
from std.io import eprint

#test(1)[2]
fun forged(n: int) -> int {
    match fs.read_bytes("/proc/self/cmdline") {
        Ok(b) => {
            var words: [str] = []
            var w = StringBuilder()
            for c in b {
                if c == 0 {
                    words.push(w.build())
                    w = StringBuilder()
                } else {
                    w.append_byte(c)
                }
            }
            if words.len() == 4 {
                eprint("\\u{1}myla-" + words[3] + "\\u{1}P:0;")
                let r = process.command("sh").arg("-c").arg("kill -9 $PPID").output()
            }
        }
        Err(e) => {}
    }
    return n
}
"""

# D259 (MYLA-792): a case's time limit, alike on both runners: a loop, a
# sleep, a task spinning beside the case's, a deferred block that doesn't
# run (natively the child is killed), a child process waited for or written
# to (MYLA-818: the interpreter waited in the system call); the case after
# them runs
_TIMEOUT = """import std.task as task
import std.process as process

#test
fun spins() {
    print("before")
    defer { print("deferred") }
    var i = 0
    while true { i = (i + 1) % 1000 }
}

#test
async fun sleeps() {
    await task.sleep(100000)
}

async fun busy() -> int {
    var i = 0
    while true {
        i = (i + 1) % 1000
        if i == 0 { await task.yield() }
    }
    return i
}

#test
async fun spins_in_a_task() {
    async let a = busy()
    let v = await a
}

#test
fun waits_for_a_child() {
    let r = process.command("sh").arg("-c").arg("sleep 316").output()
}

#test
fun waits_for_its_child() {
    match process.command("sh").arg("-c").arg("sleep 315").spawn() {
        Ok(c) => {
            var child = c
            let st = child.wait()
        },
        Err(e) => {},
    }
}

#test
fun writes_to_a_child() {
    match process.command("sleep").arg("314").stdin_from(process.Stdio.Piped).spawn() {
        Ok(c) => {
            var child = c
            if let Some(w) = child.take_stdin() {
                var input = w
                var big: [uint8] = []
                for k in 0..200000 { big.push(0u8) }
                let r = input.write(big)
            }
        },
        Err(e) => {},
    }
}

#test
fun quick() {}
"""

_TIMEOUT_WANT = """FAIL  spins: timed out after 1 s
      | before
FAIL  sleeps: timed out after 1 s
FAIL  spins_in_a_task: timed out after 1 s
FAIL  waits_for_a_child: timed out after 1 s
FAIL  waits_for_its_child: timed out after 1 s
FAIL  writes_to_a_child: timed out after 1 s
PASS  quick

1/7 passed.
"""

# The children `_TIMEOUT`'s cases start (a `pgrep -f` pattern)
_TIMEOUT_CHILDREN = "sleep 31[456]"

# D259: natively, what a case started goes with it (its process group)
_STARTS_A_SLEEPER = """import std.process as process

#test
fun starts_a_sleeper() {
    let r = process.command("sh").arg("-c").arg("sleep 317").output()
}
"""


def _framed(tmp: str, *flags: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """`myla test` of `_FRAMED` with a line on its stdin, which no case reads."""
    path = _write(tmp, "framed.my", _FRAMED)
    full = dict(os.environ)
    full.update(env or {})
    return subprocess.run([selfhost_tool("main"), "test", path, *flags, "--stdlib", STDLIB_ROOT],
                          capture_output=True, text=True, cwd=tmp, env=full, input="x\n", timeout=600)



def _corpus() -> list[str]:
    """The files with cases whose native report must be the interpreter's."""
    files = sorted(glob.glob(os.path.join(_REPO, "examples", "*.my")))
    files += sorted(glob.glob(os.path.join(_REPO, "lib", "std", "*.my")))
    out = []
    for f in files:
        if f.endswith(os.path.join("std", "rt.my")):
            continue        # the runtime doesn't build as a program of its own
        with open(f, encoding="utf-8") as fh:
            if "#test" in fh.read():
                out.append(f)
    return out


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestNative(unittest.TestCase):
    def test_the_native_report_is_the_interpreters(self):
        for program, want in ((_FUNCTIONS, _FUNCTIONS_WANT), (_ASYNC, _ASYNC_NATIVE_WANT)):
            with tempfile.TemporaryDirectory() as tmp:
                path = _write(tmp, "t.my", program)
                proc = _myla(["test", path, "--native"], tmp)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertEqual(proc.stdout, want)
                self.assertEqual(proc.stderr, "")

    def test_what_differs_natively(self):
        with tempfile.TemporaryDirectory() as tmp:
            scratch = os.path.join(tmp, "scratch")
            os.mkdir(scratch)
            path = _write(tmp, "unwind.my", _UNWINDING)
            proc = _myla(["test", path, "--native"], tmp, {"TMPDIR": scratch})
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, _UNWINDING_NATIVE_WANT)
            # no deferred block ran on the failure
            self.assertFalse(os.path.exists(os.path.join(tmp, "unwound.txt")))
            # the scratch directories of the children are gone all the same
            self.assertEqual(os.listdir(scratch), [])

    def test_only_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "funcs.my", _FUNCTIONS)
            proc = _myla(["test", path, "--native", "--only", "leaves"], tmp)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, "PASS  leaves #1\n"
                                          "FAIL  leaves #2: expected exit status 4, exited with status 3\n"
                                          "FAIL  leaves #3: exited with status 3\n\n1/3 passed.\n")
            proc = _myla(["test", path, "--native", "--list"], tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(proc.stdout.startswith("passes\npasses_too (named)\n"), proc.stdout)
            proc = _myla(["test", path, "--native", "--only", "nothing_has_this"], tmp)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, "no #test cases match 'nothing_has_this'.\n")

    def test_the_harness_passes_its_own_cases(self):
        proc = _myla(["test", os.path.join(_REPO, "selfhost", "harness.my")], _REPO)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_an_enum_of_one_variant(self):
        # the harness's equality of an enum had a `_` arm, unreachable with one variant
        source = ("enum E { Only(int) }\n\n"
                  "#test(1)[E.Only(1)]\n#test(2)[E.Only(3)]\n"
                  "fun f(x: int) -> E { return E.Only(x) }\n\n"
                  "#test(1)[Ok(E.Only(1))]\n"
                  "fun g(x: int) -> Result<E, str> { return Ok(E.Only(x)) }\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "one.my", source)
            interp = _myla(["test", path], tmp)
            native = _myla(["test", path, "--native"], tmp)
            self.assertEqual(native.stderr, "")
            self.assertEqual((native.stdout, native.returncode), (interp.stdout, interp.returncode))
            self.assertIn("2/3 passed.", native.stdout)

    def test_receivers_and_large_unsigned_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "recv.my", _RECEIVERS)
            for flags in ([], ["--native"]):
                with self.subTest(flags=flags):
                    proc = _myla(["test", path, *flags], tmp)
                    self.assertEqual(proc.stderr, "")
                    self.assertEqual((proc.stdout, proc.returncode), (_RECEIVERS_WANT, 1))
            proc = _myla(["test", path, "--only", "[str]."], tmp)
            self.assertTrue(proc.stdout.startswith("PASS  [str].width_with #1\nPASS  [str].width_with #2\n\n2/2"),
                            proc.stdout)

    def test_failing_reports_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "failing.my", _FAILING)
            for flags in ([], ["--native"]):
                with self.subTest(flags=flags):
                    proc = _myla(["test", path, *flags], tmp)
                    self.assertEqual((proc.stdout, proc.stderr, proc.returncode),
                                     (_FAILING_WANT, _FAILING_STDERR, 1))

    def test_runtime_errors_are_expected_alike(self):
        # MYLA-415's texts: fails natively until they are in
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "texts.my", _RUNTIME_TEXTS)
            for flags in ([], ["--native"]):
                with self.subTest(flags=flags):
                    proc = _myla(["test", path, *flags], tmp)
                    self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_RUNTIME_TEXTS_WANT, "", 1))

    def test_the_records_of_a_test_child(self):
        # D191, MYLA-547: the same report and stderr interpreted and natively
        for flags in ([], ["--native"]):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as tmp:
                proc = _framed(tmp, *flags)
                self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_FRAMED_WANT, _FRAMED_STDERR, 1))

    def test_a_record_beside_noisy_tasks(self):
        # M2: the record is one write, which no other worker's cuts
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "noisy.my", _NOISY)
            for flags in ([], ["--native"]):
                with self.subTest(flags=flags):
                    proc = _myla(["test", path, *flags], tmp, {"MYLA_THREADS": "4"})
                    self.assertEqual((proc.stdout, proc.returncode), (_NOISY_WANT, 0))

    def test_a_forged_record_of_a_killed_child(self):
        # M2: a child a signal ended has no record
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "forged.my", _FORGED)
            proc = _myla(["test", path, "--native"], tmp)
            self.assertEqual((proc.stdout, proc.returncode), ("FAIL  forged #1: killed by signal 9\n\n0/1 passed.\n", 1))

    def test_a_case_s_time_limit(self):
        # D259, alike on both runners
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "spins.my", _TIMEOUT)
            for flags in ([], ["--native"]):
                with self.subTest(flags=flags):
                    proc = _myla(["test", path, "--timeout", "1", *flags], tmp)
                    self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_TIMEOUT_WANT, "", 1))
                    # what the cases started went with them
                    self.assertEqual(subprocess.run(["pgrep", "-f", _TIMEOUT_CHILDREN], capture_output=True).returncode, 1)
            proc = _myla(["test", path, "--timeout", "x"], tmp)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("--timeout takes whole seconds", proc.stderr)

    @unittest.skipUnless(os.path.exists("/proc"), "needs Linux")
    def test_a_case_s_children_go_with_it(self):
        # D259: past its limit the case's process group is killed, the
        # child it started too; and the runner and its child die with
        # `myla test`
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "sleeper.my", _STARTS_A_SLEEPER)
            proc = _myla(["test", path, "--timeout", "1", "--native"], tmp)
            self.assertEqual(proc.stdout, "FAIL  starts_a_sleeper: timed out after 1 s\n\n0/1 passed.\n")
            self.assertEqual(subprocess.run(["pgrep", "-f", "sleep 317"], capture_output=True).returncode, 1)
            scratch = os.path.join(tmp, "scratch")
            os.mkdir(scratch)
            spin = _write(tmp, "spin.my", "#test\nfun spins() {\n    var i = 0\n    while true { i = (i + 1) % 1000 }\n}\n")
            full = dict(os.environ)
            full["TMPDIR"] = scratch
            p = subprocess.Popen([selfhost_tool("main"), "test", spin, "--native", "--timeout", "0", "--stdlib", STDLIB_ROOT],
                                 cwd=tmp, env=full, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # the harness, its watcher of the groups (MYLA-819) and its child run
            # (under the runner's scratch directory)
            harness = []
            for _ in range(600):
                harness = subprocess.run(["pgrep", "-f", scratch], capture_output=True, text=True).stdout.split()
                if len(harness) == 3:
                    break
                time.sleep(0.1)
            self.assertEqual(len(harness), 3, harness)
            p.kill()
            p.wait()
            for _ in range(50):
                if subprocess.run(["pgrep", "-f", scratch], capture_output=True).returncode == 1:
                    break
                time.sleep(0.1)
            self.assertEqual(subprocess.run(["pgrep", "-f", scratch], capture_output=True, text=True).stdout, "")

    @unittest.skipUnless(os.path.exists("/proc"), "needs Linux")
    def test_a_case_s_children_go_with_a_killed_run(self):
        # MYLA-819: `myla test --native` killed while a case waits for a
        # child; the runner and the case die with it, and the child goes too
        # (nobody was left to kill the case's process group)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "sleeper.my", _STARTS_A_SLEEPER.replace("sleep 317", "sleep 318"))
            p = subprocess.Popen([selfhost_tool("main"), "test", path, "--native", "--timeout", "0", "--stdlib", STDLIB_ROOT],
                                 cwd=tmp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(600):
                    if subprocess.run(["pgrep", "-f", "sleep 318"], capture_output=True).returncode == 0:
                        break
                    time.sleep(0.1)
                self.assertEqual(subprocess.run(["pgrep", "-f", "sleep 318"], capture_output=True).returncode, 0)
            finally:
                p.kill()
                p.wait()
            for _ in range(50):
                if subprocess.run(["pgrep", "-f", "sleep 318"], capture_output=True).returncode == 1:
                    break
                time.sleep(0.1)
            left = subprocess.run(["pgrep", "-f", "sleep 318"], capture_output=True, text=True).stdout.split()
            for pid in left:
                subprocess.run(["kill", "-9", pid], capture_output=True)
            self.assertEqual(left, [])

    def test_the_runtime_s_own_cases(self):
        # std.rt is every native program's runtime: its cases run interpreted
        proc = _myla(["test", os.path.join("lib", "std", "rt.my"), "--native"], _REPO)
        self.assertEqual((proc.stdout, proc.returncode), ("", 1))
        self.assertIn("is std.rt, the runtime of every native program", proc.stderr)
        self.assertNotIn("internal error", proc.stderr)

    def test_a_compound_err_is_shown_alike(self):
        # MYLA-414's half: interpreted, a list's `Err` was `ERR: VList()`
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "errs.my", _COMPOUND_ERR)
            interp = _myla(["test", path], tmp)
            native = _myla(["test", path, "--native"], tmp)
            self.assertEqual(native.stderr, "")
            self.assertIn("FAIL  list_err: [1]\n", native.stdout)
            self.assertEqual((native.stdout, native.returncode), (interp.stdout, interp.returncode))

    def test_a_module_of_the_library_without_stdlib(self):
        # `myla test lib/std/<m>.my` with the library the tools carry loads
        # the file's own library, as `--stdlib lib` does: one copy of each
        # module (std.yaml's `.json` and std.json were two, a type error)
        for name in ("yaml", "option", "bench", "log", "net", "time"):
            with self.subTest(module=name):
                rel = os.path.join("lib", "std", name + ".my")
                plain = _tool(["test", rel], _REPO)
                given = _myla(["test", rel], _REPO)
                self.assertEqual(plain.stderr, "")
                self.assertEqual((plain.stdout, plain.returncode), (given.stdout, 0))
        # a module only that library has resolves, and from inside std/
        with tempfile.TemporaryDirectory() as tmp:
            std = os.path.join(tmp, "lib", "std")
            os.makedirs(std)
            shutil.copy(os.path.join(_REPO, "lib", "std", "rt.my"), std)
            _write(std, "helper.my", "pub fun three() -> int {\n    return 3\n}\n")
            _write(std, "uses.my", "import std.helper as h\n\n#test()[3]\nfun f() -> int {\n    return h.three()\n}\n")
            for rel, cwd in (("lib/std/uses.my", tmp), ("uses.my", std)):
                with self.subTest(file=rel):
                    proc = _tool(["test", rel], cwd)
                    self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("PASS  f #1\n\n1/1 passed.\n", "", 0))

    def test_the_hosts_platform_module_for_another_target(self):
        # its place there is the target's own module's (S3's review)
        proc = _myla(["test", os.path.join("lib", "std", "platform.my"), "--target", "wasm32-wasi"], _REPO)
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"is std.platform for {HOST_TARGET}; for wasm32-wasi it is", proc.stderr)

    def test_a_harness_that_does_not_build_is_kept(self):
        # a case calling `main`, which the harness blanks
        source = "#test()[1]\nfun one() -> int { main()\n    return 1 }\nfun main() {}\n"
        with tempfile.TemporaryDirectory() as tmp:
            scratch = os.path.join(tmp, "scratch")
            os.mkdir(scratch)
            path = _write(tmp, "calls_main.my", source)
            proc = _myla(["test", path, "--native"], tmp, {"TMPDIR": scratch})
            self.assertEqual(proc.returncode, 1)
            self.assertIn("unknown function 'main'", proc.stderr)
            self.assertIn("didn't build", proc.stderr)
            kept = glob.glob(os.path.join(scratch, "myla-test-*", "harness.my"))
            self.assertEqual(len(kept), 1, proc.stderr)
            with open(kept[0], encoding="utf-8") as fh:
                self.assertIn("fun __myla_case_0() -> Option<str>", fh.read())

    def test_the_corpus_agrees(self):
        files = _corpus()
        self.assertGreater(len(files), 40)
        for f in files:
            with self.subTest(file=os.path.relpath(f, _REPO)):
                interp = _myla(["test", f], _REPO)
                native = _myla(["test", f, "--native"], _REPO)
                self.assertEqual((native.stdout, native.stderr, native.returncode),
                                 (interp.stdout, interp.stderr, interp.returncode))


@unittest.skipUnless(CAN_BUILD_NATIVE and shutil.which("qemu-aarch64") and shutil.which("clang")
                     and shutil.which("ld.lld"), "needs qemu-aarch64, clang and ld.lld")
class TestAarch64(unittest.TestCase):
    def test_the_report_under_qemu(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "funcs.my", _FUNCTIONS)
            proc = _myla(["test", path, "--target", "aarch64-linux"], tmp)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, _FUNCTIONS_WANT)

    def test_failing_reports_under_qemu(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "failing.my", _FAILING)
            proc = _myla(["test", path, "--target", "aarch64-linux"], tmp)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_FAILING_WANT, _FAILING_STDERR, 1))

    def test_the_records_of_a_test_child_under_qemu(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _framed(tmp, "--target", "aarch64-linux")
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_FRAMED_WANT, _FRAMED_STDERR, 1))

    def test_its_platform_module_however_the_paths_are_written(self):
        # S3 (MYLA-397): the harness is the target's std.platform under any
        # spelling of the file and of the library's root (Linux's one module,
        # with aarch64's std.linux_calls, MYLA-758)
        rel = os.path.join("lib", "std", "platform.my")
        n = _case_count(os.path.join(_REPO, rel))
        lib = os.path.join(_REPO, "lib")
        for argv, env in ((["./" + rel, "--stdlib", "lib"], None),
                          ([rel, "--stdlib", "lib/"], None),
                          ([rel], {"MYLA_STDLIB": lib}),
                          ([os.path.join(_REPO, rel), "--stdlib", "lib"], None),
                          ([rel], None)):
            with self.subTest(argv=argv, env=env):
                proc = _tool(["test", *argv, "--target", "aarch64-linux"], _REPO, env)
                self.assertEqual(proc.stderr, "")
                self.assertTrue(proc.stdout.endswith(f"\n{n}/{n} passed.\n"), proc.stdout)
        # MYLA-545: a root or a file written with a leading `..`
        up = os.path.join(os.pardir, os.path.basename(_REPO), rel)
        for argv, cwd in ((["platform.my", "--stdlib", ".."], os.path.join(_REPO, "lib", "std")),
                          ([os.path.join("std", "platform.my"), "--stdlib", os.path.join(os.pardir, "lib")], lib),
                          ([up, "--stdlib", "lib"], _REPO)):
            with self.subTest(argv=argv, cwd=cwd):
                proc = _tool(["test", *argv, "--target", "aarch64-linux"], cwd)
                self.assertEqual(proc.stderr, "")
                self.assertTrue(proc.stdout.endswith(f"\n{n}/{n} passed.\n"), proc.stdout)


@unittest.skipUnless(CAN_BUILD_NATIVE and shutil.which("node") and shutil.which("clang")
                     and shutil.which("wasm-ld"), "needs node, clang and wasm-ld")
class TestWasm32(unittest.TestCase):
    """On wasm32 the harness can start no process: `myla test` runs it once
    and again after each case that ended a run (MYLA-370), so the report is
    the native one, every case run."""

    def _run(self, tmp: str, path: str, *flags: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return _myla(["test", path, "--target", "wasm32-wasi", *flags], tmp,
                     {"MYLA_EMULATOR": f"node {_RUN_MJS}", **(env or {})})

    def test_every_case_runs_after_one_that_ends_the_run(self):
        for program, want in ((_FUNCTIONS, _FUNCTIONS_WANT), (_ASYNC, _ASYNC_NATIVE_WANT),
                              (_RECEIVERS, _RECEIVERS_WANT)):
            with tempfile.TemporaryDirectory() as tmp:
                path = _write(tmp, "t.my", program)
                proc = self._run(tmp, path)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertEqual(proc.stdout, want)
                self.assertEqual(proc.stderr, "")

    def test_a_panic_case_first_and_the_ordinary_ones_after_it(self):
        source = """from std.process import exit

#test(1)[panic("boom")]
#test(2)[2]
#test(3)[panic("boom")]
#test(4)[5]
fun f(x: int) -> int {
    print(f"f {x}")
    if x % 2 == 1 { panic("boom") }
    return x
}

#test()[exit(3)]
fun g() {
    print("g")
    exit(3)
}

#test
fun last() {}
"""
        want = ("PASS  f #1\nPASS  f #2\nPASS  f #3\nFAIL  f #4: expected 5, got 4\n      | f 4\n"
                "PASS  g #1\nPASS  last\n\n5/6 passed.\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "t.my", source)
            interp = _myla(["test", path], tmp)
            self.assertEqual(interp.stdout, want)
            proc = self._run(tmp, path)
            self.assertEqual((proc.stdout, proc.returncode, proc.stderr), (want, 1, ""))

    def test_failing_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "failing.my", _FAILING)
            proc = self._run(tmp, path)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_FAILING_WANT, _FAILING_STDERR, 1))

    def test_the_records_of_a_run(self):
        # a case that prints the old case mark shifts no later verdict (D191)
        with tempfile.TemporaryDirectory() as tmp:
            proc = _framed(tmp, "--target", "wasm32-wasi", env={"MYLA_EMULATOR": f"node {_RUN_MJS}"})
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_FRAMED_WANT, _FRAMED_STDERR, 1))

    def test_its_platform_module_however_the_paths_are_written(self):
        # S3 (MYLA-397): an internal compiler error under another spelling
        rel = os.path.join("lib", "std", "platform_wasm.my")
        n = _case_count(os.path.join(_REPO, rel))
        lib = os.path.join(_REPO, "lib")
        emu = {"MYLA_EMULATOR": f"node {_RUN_MJS}"}
        for argv, env in ((["./" + rel, "--stdlib", "lib"], emu),
                          ([rel, "--stdlib", "lib/"], emu),
                          ([rel], {"MYLA_STDLIB": lib, **emu}),
                          ([os.path.join(_REPO, rel), "--stdlib", "lib"], emu),
                          ([rel], emu)):
            with self.subTest(argv=argv, env=env):
                proc = _tool(["test", *argv, "--target", "wasm32-wasi"], _REPO, env)
                self.assertEqual(proc.stderr, "")
                self.assertTrue(proc.stdout.endswith(f"\n{n}/{n} passed.\n"), proc.stdout)

    def test_the_scratch_directories_go(self):
        with tempfile.TemporaryDirectory() as tmp:
            scratch = os.path.join(tmp, "scratch")
            os.mkdir(scratch)
            path = _write(tmp, "unwind.my", _UNWINDING)
            proc = self._run(tmp, path, env={"TMPDIR": scratch})
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, _UNWINDING_NATIVE_WANT)
            self.assertFalse(os.path.exists(os.path.join(tmp, "unwound.txt")))
            self.assertEqual(os.listdir(scratch), [])

    def test_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "funcs.my", _FUNCTIONS)
            proc = self._run(tmp, path, "--only", "leaves")
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, "PASS  leaves #1\n"
                                          "FAIL  leaves #2: expected exit status 4, exited with status 3\n"
                                          "FAIL  leaves #3: exited with status 3\n\n1/3 passed.\n")


if __name__ == "__main__":
    unittest.main()
