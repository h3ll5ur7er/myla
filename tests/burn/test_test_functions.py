"""Burn test: test functions and what a failing case leaves behind (D162,
MYLA-304).

A bare `#test` on a function without parameters makes it a test function:
`myla test` runs it and reports it by its name, `PASS  passes`; a result of
`Result<(), E>` fails the case on `Err(e)` with `e` shown. `std.test` has the
checks (`expect`, `expect_eq`, `expect_ne`, `fail`) and `temp_dir`, a scratch
directory the runner removes when the case ends. `[panic("message")]` and
`[exit(n)]` are expected values. A failed case unwinds its deferred blocks,
and a deferred block that fails is reported with the case. What a case
printed is shown under its FAIL line only. `--only <text>` and `--list`
select and name the cases. A `#test` on an async function runs the case as
the entry task of a program of its own (MYLA-305)."""
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_FUNCTIONS = """import std.test as test
from std.process import exit

#test
fun passes() {
    test.expect(1 + 1 == 2)
}

#test // named
fun passes_too() -> Result<(), str> {
    return Ok(())
}

#test
fun fails_by_err() -> Result<(), str> {
    return Err("accepted 80")
}

#test
fun fails_by_expect() {
    test.expect_eq(3, 4)
}

#test
fun fails_by_ne() {
    test.expect_ne("a", "a")
}

#test
fun fails_by_fail() {
    print("partial")
    test.fail("not yet")
}

#test(1, 0)[panic("division by zero")]
#test(4, 2)[2]
#test(4, 2)[panic("division by zero")]
#test(1, 0)[panic("something else")]
#test(1, 0)[5]
fun div(a: int, b: int) -> int {
    return a / b
}

#test()[exit(3)]
#test()[exit(4)]
#test()[()]
fun leaves() {
    exit(3)
}

#test()[exit(3)]
fun stays() {}

fun main() {}
"""

_FUNCTIONS_WANT = """PASS  passes
PASS  passes_too (named)
FAIL  fails_by_err: accepted 80
FAIL  fails_by_expect: runtime error: expected 4, got 3
FAIL  fails_by_ne: runtime error: expected two different values, both are a
FAIL  fails_by_fail: runtime error: not yet
      | partial
PASS  div #1
PASS  div #2
FAIL  div #3: expected runtime error 'division by zero', got 2
FAIL  div #4: expected runtime error 'something else', got runtime error 'division by zero'
FAIL  div #5: runtime error: division by zero
PASS  leaves #1
FAIL  leaves #2: expected exit status 4, exited with status 3
FAIL  leaves #3: exited with status 3
FAIL  stays #1: expected exit status 3, the call returned

5/15 passed.
"""

_UNWINDING = """import std.test as test
import std.fs as fs
from std.fs import IoError
from std.process import exit

fun inner() {
    defer { print("inner's defer") }
    panic("boom")
}

#test
fun unwinds_nested_blocks() {
    defer { print("outer's defer") }
    if true {
        defer { print("block's defer") }
        inner()
    }
    print("not reached")
}

#test
fun unwinds_on_exit() {
    defer { let w = fs.write_to_file("unwound.txt", "yes") }
    exit(2)
}

#test
fun reports_a_failing_defer() {
    defer { panic("bang") }
    defer { print("still runs") }
    panic("boom")
}

#test
fun passes_and_cleans() -> Result<(), IoError> {
    let d = test.temp_dir()
    let e = test.temp_dir()
    test.expect_ne(d, e)
    test.expect(fs.is_dir(d))
    fs.write_to_file(d + "/a.txt", "hello")?
    test.expect_eq(fs.read_to_string(d + "/a.txt")?, "hello")
    return Ok(())
}

#test
fun fails_with_an_io_error() -> Result<(), IoError> {
    let text = fs.read_to_string("/nowhere/at/all")?
    return Ok(())
}

#test
fun fails_and_cleans() {
    let d = test.temp_dir()
    let w = fs.write_to_file(d + "/a.txt", "hello")
    test.fail("after writing")
}

#test
fun a_passing_defer_failure_fails() {
    defer { panic("late") }
}

#test
fun output_of_a_pass_is_hidden() {
    print("hidden")
}

fun main() {}
"""

_UNWINDING_WANT = """FAIL  unwinds_nested_blocks: runtime error: boom
      | inner's defer
      | block's defer
      | outer's defer
FAIL  unwinds_on_exit: exited with status 2
FAIL  reports_a_failing_defer: runtime error: boom; deferred block: runtime error: bang
      | still runs
PASS  passes_and_cleans
FAIL  fails_with_an_io_error: not found (NotFound)
FAIL  fails_and_cleans: runtime error: after writing
FAIL  a_passing_defer_failure_fails: deferred block: runtime error: late
PASS  output_of_a_pass_is_hidden

2/8 passed.
"""

_ASYNC = """import std.test as test
import std.task as task

actor Counter {
    n: int,
}

impl Counter {
    async fun bump(var self, by: int) {
        self.n = self.n + by
    }

    async fun get(self) -> int {
        return self.n
    }
}

async fun bump_many(c: Counter, times: int) {
    var i = 0
    while i < times {
        await c.bump(1)
        i = i + 1
    }
}

#test
async fun counts_in_parallel() {
    let c = Counter { n: 0 }
    async let a = bump_many(c, 100)
    async let b = bump_many(c, 100)
    await a
    await b
    test.expect_eq(await c.get(), 200)
}

#test(3)[6]
#test(4)[9]
async fun doubled(n: int) -> int {
    let c = Counter { n: 0 }
    await c.bump(n)
    await c.bump(n)
    return await c.get()
}

async fun child_that_fails() {
    await task.yield()
    panic("child boom")
}

#test
async fun a_childs_failure_fails_the_case() {
    defer { print("case's defer") }
    async let k = child_that_fails()
    // until the child's failure stops it, at an `await` (D97): ten yields
    // were a race natively, where the child runs on another worker
    while true {
        await task.yield()
    }
    print("not reached")
}

#test
async fun unwinds_an_async_case() {
    defer { print("async defer ran") }
    let c = Counter { n: 0 }
    await c.bump(1)
    test.expect_eq(await c.get(), 2)
}

#test
async fun passes_after_a_failed_one() -> Result<(), str> {
    let c = Counter { n: 5 }
    if await c.get() != 5 { return Err("state leaked") }
    return Ok(())
}

fun main() {}
"""

_ASYNC_WANT = """PASS  counts_in_parallel
PASS  doubled #1
FAIL  doubled #2: expected 9, got 8
FAIL  a_childs_failure_fails_the_case: runtime error: child boom
      | case's defer
FAIL  unwinds_an_async_case: runtime error: expected 2, got 1
      | async defer ran
PASS  passes_after_a_failed_one

3/6 passed.
"""

# a failure outside `myla test` still runs no deferred block (D141)
_PROGRAM = """import std.fs as fs

fun main() {
    defer { let w = fs.write_to_file("unwound.txt", "yes") }
    panic("boom")
}
"""


def _myla(args: list[str], cwd: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full = dict(os.environ)
    full.update(env or {})
    return subprocess.run([selfhost_tool("main"), *args, "--stdlib", STDLIB_ROOT],
                          capture_output=True, text=True, cwd=cwd, env=full)


def _write(tmp: str, name: str, source: str) -> str:
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(source)
    return path


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestTestFunctions(unittest.TestCase):
    def test_test_functions_expectations_and_expected_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "funcs.my", _FUNCTIONS)
            proc = _myla(["test", path], tmp)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, _FUNCTIONS_WANT)
            self.assertEqual(proc.stderr, "")

    def test_a_failed_case_unwinds_and_its_scratch_directory_goes(self):
        with tempfile.TemporaryDirectory() as tmp:
            scratch = os.path.join(tmp, "scratch")
            os.mkdir(scratch)
            path = _write(tmp, "unwind.my", _UNWINDING)
            proc = _myla(["test", path], tmp, {"TMPDIR": scratch})
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, _UNWINDING_WANT)
            # `exit` unwound through the deferred block that wrote the file
            with open(os.path.join(tmp, "unwound.txt"), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "yes")
            # every case's scratch root is gone, the failed cases' too
            self.assertEqual(os.listdir(scratch), [])

    def test_async_cases_run_as_the_entry_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "async.my", _ASYNC)
            proc = _myla(["test", path], tmp)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, _ASYNC_WANT)
            self.assertEqual(proc.stderr, "")

    def test_a_program_still_runs_no_deferred_block_on_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "prog.my", _PROGRAM)
            proc = _myla(["run", path], tmp)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("runtime error: boom", proc.stderr)
            self.assertFalse(os.path.exists(os.path.join(tmp, "unwound.txt")))

    def test_only_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "funcs.my", _FUNCTIONS)
            proc = _myla(["test", path, "--list"], tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, "passes\npasses_too (named)\nfails_by_err\nfails_by_expect\nfails_by_ne\n"
                                          "fails_by_fail\ndiv #1\ndiv #2\ndiv #3\ndiv #4\ndiv #5\n"
                                          "leaves #1\nleaves #2\nleaves #3\nstays #1\n")
            proc = _myla(["test", path, "--only", "leaves"], tmp)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, "PASS  leaves #1\n"
                                          "FAIL  leaves #2: expected exit status 4, exited with status 3\n"
                                          "FAIL  leaves #3: exited with status 3\n\n1/3 passed.\n")
            proc = _myla(["test", path, "--only", "passes", "--list"], tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, "passes\npasses_too (named)\n")
            proc = _myla(["test", path, "--only", "nothing_has_this"], tmp)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, "no #test cases match 'nothing_has_this'.\n")

    def test_temp_dir_needs_a_running_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "outside.my", "import std.test as test\nfun main() { print(test.temp_dir()) }\n")
            proc = _myla(["run", path], tmp)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("runtime error: test.temp_dir() needs a running case: run the file with 'myla test'",
                          proc.stderr)
            # natively, the harness of `myla test --native` names the case's
            # directory in MYLA_TEST_DIR; without it there is no case either
            exe = os.path.join(tmp, "outside")
            built = _myla(["build", path, "-o", exe], tmp)
            self.assertEqual(built.returncode, 0, built.stderr)
            proc = subprocess.run([exe], capture_output=True, text=True, cwd=tmp)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("runtime error: test.temp_dir() needs a running case", proc.stderr)
            case_dir = os.path.join(tmp, "case")
            os.mkdir(case_dir)
            proc = subprocess.run([exe], capture_output=True, text=True, cwd=tmp,
                                  env={**os.environ, "MYLA_TEST_DIR": case_dir})
            self.assertEqual(proc.returncode, 0, proc.stderr)
            # `d` and 16 random hexadecimal digits (std.fs.make_temp_dir_in, MYLA-339)
            self.assertRegex(proc.stdout, "^" + re.escape(case_dir) + "/d[0-9a-f]{16}\n$")
            self.assertTrue(os.path.isdir(proc.stdout.strip()))


if __name__ == "__main__":
    unittest.main()
