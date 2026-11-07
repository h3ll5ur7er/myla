"""Burn test: `myla test --native` and `--target` (D162, MYLA-307).

`myla test --native` builds a harness program from a file and its cases
(selfhost/harness.my) and runs it: the report is the interpreter's, line
for line, on every example and standard library module with cases (but the
runtime itself, which doesn't build as a program). What differs natively by
design: a failed case runs no deferred block (its child process ends), a
runtime error's message carries no values, so an expected `[panic]` is
compared by prefix. For another target the harness runs under the emulator
`--target` implies (qemu-aarch64) or MYLA_EMULATOR names (Node for wasm32,
where no child process can start: the cases run in the harness itself and
the first runtime error ends the run, which the report says)."""
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

# on wasm32 no child process can start: the cases run in the harness, and
# the first runtime error ends the run
_FUNCTIONS_INLINE_WANT = """PASS  passes
PASS  passes_too (named)
FAIL  fails_by_err: accepted 80
FAIL  fails_by_expect: runtime error: expected 4, got 3
FAIL  fails_by_ne: not run (an earlier failure ended the run)
FAIL  fails_by_fail: not run (an earlier failure ended the run)
FAIL  div #1: not run (an earlier failure ended the run)
FAIL  div #2: not run (an earlier failure ended the run)
FAIL  div #3: not run (an earlier failure ended the run)
FAIL  div #4: not run (an earlier failure ended the run)
FAIL  div #5: not run (an earlier failure ended the run)
FAIL  leaves #1: not run (an earlier failure ended the run)
FAIL  leaves #2: not run (an earlier failure ended the run)
FAIL  leaves #3: not run (an earlier failure ended the run)
FAIL  stays #1: not run (an earlier failure ended the run)

2/15 passed.
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
    def test_the_cases_run_in_the_harness_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "funcs.my", _FUNCTIONS)
            proc = _myla(["test", path, "--target", "wasm32-wasi"], tmp,
                         {"MYLA_EMULATOR": f"node {_RUN_MJS}"})
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(proc.stdout, _FUNCTIONS_INLINE_WANT)


if __name__ == "__main__":
    unittest.main()
