"""What a hello world's `myla check` and `myla run` cost, in instructions
(D258, MYLA-793): an implicit module costs every program its share, as
std.float's 4.6 M instructions did unnoticed (22 percent of a check,
MYLA-552's and MYLA-608's follow-up). The bounds have headroom over the
count measured; an implicit module added, or a start-up made dearer by as
much, goes past them.

Instructions are counted, not timed, so that a loaded machine doesn't
matter: by valgrind's callgrind where it is installed, else by `perf stat`
(user space), else the test is skipped."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from ._tools import selfhost_tool

HELLO = 'fun main() {\n    print("hello")\n}\n'

# The counts of 2026-11-18 at e659342 (round 7's wave A), with the library
# the tools carry: `check` 25,494,608 and `run` 28,859,804 by callgrind,
# MYLA_THREADS=1. The bounds are 10 percent over them (an implicit module of
# std.float's size is about 18 percent); lower them when a change makes the
# start cheaper (std.float made lazy, D258), so that they keep guarding.
BOUNDS = {"check": 28_000_000, "run": 31_700_000}


def counter() -> str:
    """"valgrind", "perf", or "" where neither counts here."""
    if shutil.which("valgrind"):
        proc = subprocess.run(["valgrind", "--tool=callgrind", "--callgrind-out-file=/dev/null", "true"],
                              capture_output=True, text=True)
        if proc.returncode == 0 and "Collected" in proc.stderr:
            return "valgrind"
    if shutil.which("perf"):
        proc = subprocess.run(["perf", "stat", "-x,", "-e", "instructions:u", "true"], capture_output=True, text=True)
        if proc.returncode == 0 and re.search(r"^\d+,", proc.stderr, re.M):
            return "perf"
    return ""


COUNTER = counter()


def instructions(argv: list[str], cwd: str) -> int:
    """The instructions `argv` runs, as COUNTER counts them."""
    env = dict(os.environ, MYLA_THREADS="1")
    env.pop("MYLA_STDLIB", None)
    if COUNTER == "valgrind":
        proc = subprocess.run(["valgrind", "--tool=callgrind", "--callgrind-out-file=/dev/null", *argv],
                              capture_output=True, text=True, cwd=cwd, env=env, timeout=600)
        m = re.search(r"Collected : (\d+)", proc.stderr)
    else:
        proc = subprocess.run(["perf", "stat", "-x,", "-e", "instructions:u", *argv],
                              capture_output=True, text=True, cwd=cwd, env=env, timeout=600)
        m = re.search(r"^(\d+),", proc.stderr, re.M)
    if proc.returncode != 0 or not m:
        raise AssertionError(f"{' '.join(argv)} under {COUNTER} failed:\n{proc.stdout[-1000:]}{proc.stderr[-2000:]}")
    return int(m.group(1))


@unittest.skipUnless(COUNTER, "no instruction counter (valgrind or perf) here")
class HelloWorldCost(unittest.TestCase):
    def test_check_and_run_stay_within_their_bounds(self) -> None:
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "hello.my"), "w", encoding="utf-8") as fh:
                fh.write(HELLO)
            for cmd, bound in BOUNDS.items():
                with self.subTest(cmd=cmd):
                    n = instructions([myla, cmd, "hello.my"], tmp)
                    self.assertLessEqual(n, bound, f"`myla {cmd}` of a hello world ran {n:,} instructions "
                                         f"(bound {bound:,}, by {COUNTER}): did a module become implicit, "
                                         "or the start dearer? (D258)")


if __name__ == "__main__":
    unittest.main()
