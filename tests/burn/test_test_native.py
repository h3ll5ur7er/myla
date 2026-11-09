"""Burn test: `myla test --native` and `--target` (D162, MYLA-307).

`myla test --native` builds a harness program from a file and its cases
(selfhost/harness.my) and runs it: the report is the interpreter's, line
for line, on every example and standard library module with cases (but the
runtime itself, which doesn't build as a program). What differs natively by
design: a failed case runs no deferred block (its child process ends), a
runtime error's message carries no values, so an expected `[panic]` is
compared by prefix. For another target the harness runs under the emulator
`--target` implies (qemu-aarch64) or MYLA_EMULATOR names (Node for wasm32,
where the harness can start no child process: `myla test` runs it, and again
after each case that ended a run, MYLA-370)."""
import glob
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool
from tests.burn.test_test_functions import _ASYNC, _ASYNC_WANT, _FUNCTIONS, _FUNCTIONS_WANT, _UNWINDING, _myla, _write

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_RUN_MJS = os.path.join(_REPO, "tools", "wasm", "run.mjs")

# natively a failed case runs no deferred block, so nothing is printed by
# them and a deferred block's own failure isn't seen; a deferred block that
# fails on a normal return is the runtime error it raises
_UNWINDING_NATIVE_WANT = """FAIL  unwinds_nested_blocks: runtime error: boom
FAIL  unwinds_on_exit: exited with status 2
FAIL  reports_a_failing_defer: runtime error: boom
PASS  passes_and_cleans
FAIL  fails_with_an_io_error: IoError.NotFound
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
                self.assertIn("fun __myla_case_0() -> str", fh.read())

    def test_the_corpus_agrees(self):
        files = _corpus()
        self.assertGreater(len(files), 40)
        for f in files:
            with self.subTest(file=os.path.relpath(f, _REPO)):
                interp = _myla(["test", f], _REPO)
                native = _myla(["test", f, "--native"], _REPO)
                self.assertEqual(native.stderr, "", native.stderr)
                self.assertEqual((native.stdout, native.returncode), (interp.stdout, interp.returncode))


@unittest.skipUnless(CAN_BUILD_NATIVE and shutil.which("qemu-aarch64") and shutil.which("clang")
                     and shutil.which("ld.lld"), "needs qemu-aarch64, clang and ld.lld")
class TestAarch64(unittest.TestCase):
    def test_the_report_under_qemu(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "funcs.my", _FUNCTIONS)
            proc = _myla(["test", path, "--target", "aarch64-linux"], tmp)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, _FUNCTIONS_WANT)


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
