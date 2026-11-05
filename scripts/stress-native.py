#!/usr/bin/env python3
"""stress-native.py [--myla build/myla] [--runs 10]: the concurrency stress
programs (tests/burn/concurrency_stress/) built for this machine by `myla`
and run `runs` times each on 1, 4 and 16 workers, against what Myla
guarantees for them (tests/burn/test_concurrency_stress.EXPECTED).

The burn suite runs them on x86-64; this runs them on any machine the
toolchain bootstraps on, such as an aarch64 one, whose weaker memory order
the runtime's protocols must hold under too (MYLA-267, MYLA-268). CI's
bootstrap-arm64 job runs it on GitHub's arm64 runner.

Exit status 0 when every run printed what was expected."""
import argparse
import os
import subprocess
import sys
import tempfile

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, _REPO)
from tests.burn.test_concurrency_stress import EXPECTED, _DIR, _run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--myla", default=os.path.join(_REPO, "build", "myla"))
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--only", action="append", default=[], help="a program's name (repeatable); default: all")
    ap.add_argument("--workers", default="1,4,16", help="the worker counts, comma-separated")
    args = ap.parse_args()
    counts = args.workers.split(",")
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, want in sorted(EXPECTED.items()):
            if args.only and name not in args.only:
                continue
            exe = os.path.join(tmp, name)
            built = subprocess.run([args.myla, "build", os.path.join(_DIR, name + ".my"), "-o", exe],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                print(f"FAIL {name}: build failed\n{built.stderr}")
                failures += 1
                continue
            bad = 0
            for workers in counts:
                for _ in range(args.runs):
                    got = _run([exe], dict(os.environ, MYLA_THREADS=workers))
                    if got != want:
                        bad += 1
                        how = f"signal {-got[1]}" if got[1] < 0 else f"exit {got[1]}"
                        print(f"FAIL {name} on {workers} workers ({how}): {got[0]!r}, expected {want!r}")
            failures += bad
            print(f"{'ok  ' if bad == 0 else 'FAIL'} {name} ({len(counts) * args.runs} runs, {bad} failed)")
    print(f"{failures} failed runs")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
