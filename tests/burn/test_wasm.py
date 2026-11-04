"""The wasm32-wasi backend (MYLA-158, D125): programs built with `--target
wasm32-wasi` (selfhost/ir_wasm.my, selfhost/runtime_wasm.my and
lib/std/platform_wasm.my), assembled by clang, linked by wasm-ld and run
under Node through tools/wasm/run.mjs (our WASI shim), give what the same
programs built for x86-64 give (stdout, stderr and the exit code). The
x86-64 build is the reference: its own tests hold it to the interpreter.

Skipped where node, clang (with its wasm32 target) or wasm-ld is missing.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, native_compiler
from . import test_time
from .test_aarch64 import PROGRAMS, build_x86, run

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
RUNNER = os.path.join(_REPO, "tools", "wasm", "run.mjs")


def _have_wasm() -> bool:
    if not all(shutil.which(t) for t in ("node", "clang", "wasm-ld")):
        return False
    p = subprocess.run(["clang", "--print-targets"], capture_output=True, text=True)
    return "wasm32" in p.stdout


HAVE_WASM = _have_wasm()
WASM_SKIP = "the wasm tests need node, clang with its wasm32 target and wasm-ld"

# V8's stack for deep recursion (the main thread's is 8 MiB)
NODE = ["node", "--stack-size=7000", RUNNER]


def build_wasm(src: str, out: str) -> None:
    with open(out + ".s", "wb") as fh:
        subprocess.run([native_compiler(), src, STDLIB_ROOT, "--target", "wasm32-wasi"], stdout=fh, check=True, cwd=_REPO)
    subprocess.run(["clang", "--target=wasm32-wasi", "-mtail-call", "-mbulk-memory", "-mnontrapping-fptoint", "-msign-ext",
                    "-c", "-o", out + ".o", out + ".s"], check=True)
    subprocess.run(["wasm-ld", "-z", "stack-size=8388608", "-o", out, out + ".o"], check=True)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WASM, WASM_SKIP)
class WasmParity(unittest.TestCase):
    def same(self, src: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xb, wb = os.path.join(tmp, "x86"), os.path.join(tmp, "prog.wasm")
            build_x86(src, xb)
            build_wasm(src, wb)
            self.assertEqual(run(NODE + [wb]), run([xb]))

    def test_examples(self):
        for path in sorted(glob.glob(os.path.join(_REPO, "examples", "*.my"))):
            with self.subTest(example=os.path.basename(path)):
                self.same(path)

    def test_programs(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in PROGRAMS.items():
                with self.subTest(program=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w") as fh:
                        fh.write(source.lstrip())
                    self.same(path)

    def test_memory_grows_under_the_runner(self):
        # Node's own WASI crashed when the memory grew between two calls; the
        # runner's shim reads it afresh each time
        source = ("fun main() {\n    var lists: [[int]] = []\n    var k = 0\n    while k < 40 {\n"
                  "        var xs: [int] = []\n        var i = 0\n        while i < 500000 {\n"
                  "            xs.push(i)\n            i += 1\n        }\n        lists.push(xs)\n"
                  "        print(k)\n        k += 1\n    }\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "grow.my")
            with open(path, "w") as fh:
                fh.write(source)
            wb = os.path.join(tmp, "grow.wasm")
            build_wasm(path, wb)
            self.assertEqual(run(NODE + [wb]), ("".join(f"{k}\n" for k in range(40)), "", 0))

    def test_files(self):
        # files and directories through WASI: written, read, listed, renamed
        # and removed, a relative path against the working directory
        source = ("import std.fs as fs\n\nfun main() {\n"
                  "    match fs.make_dir(\"wd\") { Ok(n) => {}, Err(e) => { print(\"mkdir failed\") } }\n"
                  "    match fs.write_to_file(\"wd/a.txt\", \"one\\ntwo\\n\") { Ok(n) => { print(n) }, Err(e) => { print(\"write failed\") } }\n"
                  "    match fs.read_to_string(\"wd/a.txt\") { Ok(s) => { print(s.len()) }, Err(e) => { print(\"read failed\") } }\n"
                  "    print(fs.exists(\"wd/a.txt\"))\n    print(fs.is_dir(\"wd\"))\n"
                  "    match fs.rename(\"wd/a.txt\", \"wd/b.txt\") { Ok(n) => {}, Err(e) => { print(\"rename failed\") } }\n"
                  "    match fs.list_dir(\"wd\") { Ok(xs) => { for x in xs { print(x) } }, Err(e) => { print(\"list failed\") } }\n"
                  "    match fs.remove_file(\"wd/b.txt\") { Ok(n) => {}, Err(e) => { print(\"rm failed\") } }\n"
                  "    match fs.remove_dir(\"wd\") { Ok(n) => {}, Err(e) => { print(\"rmdir failed\") } }\n"
                  "    print(fs.exists(\"wd\"))\n"
                  "    match fs.read_to_string(\"missing.txt\") { Ok(s) => { print(s) }, Err(e) => { print(\"missing\") } }\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "files.my")
            with open(path, "w") as fh:
                fh.write(source)
            xb, wb = os.path.join(tmp, "x86"), os.path.join(tmp, "files.wasm")
            build_x86(path, xb)
            build_wasm(path, wb)
            want = subprocess.run([xb], capture_output=True, text=True, cwd=tmp)
            got = subprocess.run(NODE + [wb], capture_output=True, text=True, cwd=tmp)
            self.assertEqual((got.stdout, got.stderr, got.returncode), (want.stdout, want.stderr, want.returncode))
            self.assertIn("8\n", want.stdout)

    def test_compiler(self):
        # the compiler built for wasm makes the same assembly as the one built
        # for x86-64, for either target
        with tempfile.TemporaryDirectory() as tmp:
            gen = os.path.join(tmp, "gen.wasm")
            build_wasm("selfhost/gen_main.my", gen)
            for extra in ([], ["--target", "wasm32-wasi"]):
                with self.subTest(target=extra):
                    src = os.path.join(_REPO, "examples", "maps.my")
                    want = run([native_compiler(), src, STDLIB_ROOT] + extra)
                    got = run(NODE + [gen, src, STDLIB_ROOT] + extra)
                    self.assertEqual(got[2], 0, got[1])
                    self.assertEqual(got, want)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WASM, WASM_SKIP)
class WasmTasks(unittest.TestCase):
    def test_stress_programs(self):
        # the concurrency stress programs on one worker (D125), in each order
        from .test_concurrency_stress import EXPECTED, SCHEDULES, _DIR
        for name, want in EXPECTED.items():
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                wb = os.path.join(tmp, name + ".wasm")
                build_wasm(os.path.join(_DIR, name + ".my"), wb)
                for extra in [{}] + [{"MYLA_SCHED": sched} for sched in SCHEDULES]:
                    p = subprocess.run(NODE + [wb], capture_output=True, text=True, timeout=120,
                                       env=dict(os.environ, **extra))
                    self.assertEqual((p.stdout, p.returncode), want, extra)


@unittest.skipUnless(HAVE_WASM, WASM_SKIP)
class WasmTime(test_time.Time):
    """test_time's programs built for wasm and run under Node (through a
    script, as the tests run the binary), on one worker whatever
    MYLA_THREADS says. Not the ones that read slow input or start a child
    process: WASI has no processes, and the shim counts a watched input as
    ready at once (a read blocks)."""

    def native(self, name: str, text: str) -> str:
        exe = os.path.join(self.dir, name)
        build_wasm(self.source(name, text), exe + ".wasm")
        with open(exe, "w", encoding="utf-8") as fh:
            fh.write(f'#!/bin/sh\nexec node --stack-size=7000 "{RUNNER}" "{exe}.wasm" "$@"\n')
        os.chmod(exe, 0o755)
        return exe

    def test_an_async_read_lets_the_other_tasks_run(self):
        self.skipTest("the WASI shim can't wait for input without blocking")

    def test_a_time_limit_around_a_read(self):
        self.skipTest("the WASI shim can't wait for input without blocking")

    def test_a_child_process_waited_for_without_blocking_the_worker(self):
        self.skipTest("WASI has no processes")

    def test_the_virtual_clock_takes_no_time(self):
        self.skipTest("the interpreter's, tested in test_time")


if __name__ == "__main__":
    unittest.main()
