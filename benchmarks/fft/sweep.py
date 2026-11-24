#!/usr/bin/env python3
"""Times C (-O2) and Myla across sizes, to see the gap past the caches (MYLA-545).

    python3 benchmarks/fft/sweep.py [--runs N]

Uses the binaries run.py built in build/bench/fft. For each power of two from
1,024 to 1,048,576 points it runs about 2^27 butterflies, pinned to one CPU,
and prints the fastest and slowest run in nanoseconds for one butterfly.
"""
import argparse
import os
import subprocess

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "build", "bench", "fft")
VARIANTS = ["c_split_O2", "myla_split", "c_complex_O2", "myla_complex"]


def spread(exe, n, rounds, runs, cpu):
    butterflies = rounds * 2 * (n // 2) * (n.bit_length() - 1)
    times = []
    for _ in range(runs):
        out = subprocess.run(["taskset", "-c", str(cpu), os.path.join(OUT, exe), str(n), str(rounds)],
                             check=True, capture_output=True, text=True).stdout.split()
        times.append(float(out[4]) * 1e9 / butterflies)
    return min(times), max(times)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    opts = ap.parse_args()
    cpu = max(os.sched_getaffinity(0))
    print(f"{'points':>8} " + " ".join(f"{v:>16}" for v in VARIANTS))
    for lg in range(10, 21):
        n = 1 << lg
        rounds = max(1, (1 << 27) // (n * lg))
        cells = [spread(v, n, rounds, opts.runs, cpu) for v in VARIANTS]
        print(f"{n:>8} " + " ".join(f"{a:7.2f}-{b:<8.2f}" for a, b in cells))


if __name__ == "__main__":
    main()
