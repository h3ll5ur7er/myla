#!/usr/bin/env python3
"""test-target.py TARGET [MODULE...] — run the burn suites for another target
(MYLA-268): the programs are built with `--target TARGET` and run under
qemu-aarch64 (aarch64-linux), Node (wasm32-wasi) or Wine (x86_64-windows,
MYLA-702), and the tests that target is excused from are skipped with their
reason. Which suites run, and the exceptions, are in tests/burn/_targets.py.
`host` runs every suite of tests/burn for the machine itself, as
`scripts/test.sh` does but in parallel and each within its limit (MYLA-926:
CI's native aarch64 runner).

Each suite runs in its own process, as many at once as there are CPUs
(`-j N` to change), and is stopped after `--limit` seconds (a program hung
under an emulator then fails its suite, with the test it was in, instead of
holding the run until CI cancels it with nothing said); each suite's result
is printed as it ends, failures' logs and the summary at the end. Exits 1 if
any suite failed."""
from __future__ import annotations

import argparse
import atexit
import concurrent.futures
import glob
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.burn import _native, _targets  # noqa: E402


def _excused(suite: unittest.TestSuite) -> unittest.TestSuite:
    """`suite` with every test its target is excused from replaced by a skip."""
    out = unittest.TestSuite()
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            out.addTest(_excused(test))
            continue
        why = _targets.excuse_for(test.id())
        if why:
            setattr(test, test._testMethodName, unittest.skip(f"{_targets.target()}: {why}")(
                getattr(test, test._testMethodName)))
        out.addTest(test)
    return out


# What each target's runs need besides the host's `as` and `ld` (the
# compiler is built natively): with none of them every suite would skip and
# the summary still say they passed (MYLA-297).
TOOLS = {
    "aarch64-linux": ["clang", "ld.lld", "qemu-aarch64"],
    "wasm32-wasi": ["clang", "wasm-ld", "node"],
    "x86_64-windows": ["clang", "llvm-dlltool", "lld-link"],
}


def missing_tools(target: str) -> list[str]:
    """The tools `target`'s runs need that aren't on PATH (Wine for Windows'
    wherever `_native.wine` finds it)."""
    # (the machine's own tools for `host`: as and ld, or Windows' LLVM tools)
    base = _native._HOST_TOOLS if target == "host" else ["as", "ld"]
    missing = [t for t in [*base, *TOOLS.get(target, [])] if shutil.which(t) is None]
    if target == "x86_64-windows" and not _native.wine():
        missing.append("wine")
    return missing


def prepare_wine() -> None:
    """Wine as Windows' emulator (D213): its command in MYLA_EMULATOR, which
    `myla test --target` and the suites' runs read, its quiet defaults, its
    prefix, and its server and services started here, before the suites
    start their programs at once (`_native.wine_env`). The server is kept
    for the whole run (`-p`), not started again for a program after each
    pause (a hello world started in 0.37 s without it, 0.1 s with it,
    2026-11-15 at 31639e8), and stopped at the end."""
    server = _native.wine_server()
    if server:
        _native.wine_env(persist="")
        atexit.register(subprocess.run, [server, "-k"], capture_output=True)
    else:
        _native.wine_env()
    # (behind `_wine_run.py`, which ends with the program, whatever
    # Wine's services still hold, MYLA-759)
    wine = _native.wine_run()
    if wine and not os.environ.get("MYLA_EMULATOR"):
        os.environ["MYLA_EMULATOR"] = " ".join(wine)


def stop_tree(proc: subprocess.Popen) -> None:
    """`proc` and everything it started stopped: its process group's SIGKILL,
    or on Windows `taskkill /F /T`, which ends the tree."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGKILL)


def run_one(module: str) -> int:
    """Run one suite in this process (the target is in MYLA_TEST_TARGET)."""
    suite = _excused(unittest.defaultTestLoader.loadTestsFromName(module))
    # each test named as it starts: a suite stopped at its limit says which
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("target", choices=[*_targets.TARGETS, "host"])
    ap.add_argument("modules", nargs="*",
                    help="suites (default: all of tests/burn/_targets.py SUITES; for host, every tests/burn/test_*.py)")
    ap.add_argument("-j", type=int, default=os.cpu_count() or 1, help="suites run at once")
    # The longest suite, test_selfhost_codegen on x86_64-windows, took 609 s
    # in CI (2026-11-18, 04d8956); once, on 4c91ba2, it was still running at
    # the job's 75 minutes.
    ap.add_argument("--limit", type=int, default=1500, help="seconds a suite may run (default 1500)")
    ap.add_argument("--one", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.target == "host":
        os.environ.pop("MYLA_TEST_TARGET", None)
    else:
        os.environ["MYLA_TEST_TARGET"] = args.target
    os.chdir(ROOT)
    if args.one:
        return run_one(args.modules[0])
    missing = missing_tools(args.target)
    if args.target == "x86_64-windows":
        prepare_wine()
    if missing:
        msg = f"{args.target}: missing {', '.join(missing)}: the suites would skip"
        if os.environ.get("MYLA_REQUIRE_TARGETS"):
            print(msg, file=sys.stderr)
            return 1
        print(f"warning: {msg}", file=sys.stderr)
    every = sorted("tests.burn." + os.path.basename(f)[:-3]
                   for f in glob.glob(os.path.join(ROOT, "tests", "burn", "test_*.py")))
    modules = ([m if m.startswith("tests.") else "tests.burn." + m for m in args.modules]
               or (every if args.target == "host" else _targets.SUITES))

    def run(module: str) -> tuple[str, int, float, str]:
        start = time.monotonic()
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as log:
            # its own process group, so that its programs stop with it (on
            # Windows a new group, its tree ended by taskkill, MYLA-926)
            group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                     else {"start_new_session": True})
            proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), args.target, module, "--one"],
                                    stdout=log, stderr=subprocess.STDOUT, **group)
            try:
                code = proc.wait(timeout=args.limit)
                note = ""
            except subprocess.TimeoutExpired:
                stop_tree(proc)
                proc.wait()
                code = 1
                note = f"\nSTOPPED after its {args.limit} s (--limit): the test above it was still running"
            log.seek(0)
            return module, code, time.monotonic() - start, log.read() + note

    failed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.j)) as pool:
        for future in concurrent.futures.as_completed([pool.submit(run, m) for m in modules]):
            module, code, secs, log = future.result()
            tail = log.strip().splitlines()[-1] if log.strip() else ""
            print(f"{'ok  ' if code == 0 else 'FAIL'} {module} ({secs:.0f} s) {tail}", flush=True)
            if code:
                failed.append((module, log))
    for module, log in failed:
        print(f"\n===== {module} =====\n{log}")
    print(f"\n{args.target}: {len(modules) - len(failed)} of {len(modules)} suites passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
