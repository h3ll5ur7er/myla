#!/usr/bin/env python3
"""Builds and times the FFT in every language (MYLA-545).

    python3 benchmarks/fft/run.py [--runs N] [--json FILE]

Variants: Myla, C (gcc -O2 and -O3 -march=native), C# and plain Python, each
in two layouts: two arrays of floats (`split`) and one array of complex
numbers (`complex`). Needs build/myla (scripts/bootstrap.sh), gcc, dotnet and
python3 on the PATH; benchLANG's `nix develop` brings the last three.

First every variant runs two small configurations and must print the same
checksum and round-trip error. Then each is timed at 4096 points (in the
cache) and 1,048,576 points (bound by memory), pinned to one CPU. Python does
fewer round trips, so the measure is the time for one butterfly: seconds /
(rounds * 2 transforms * n/2 * log2 n butterflies).
"""
import argparse
import datetime
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(REPO, "build", "bench", "fft")

CHECKS = [(4096, 3), (65536, 2)]
SIZES = [4096, 1 << 20]
ROUNDS = {"native": {4096: 10000, 1 << 20: 10}, "python": {4096: 200, 1 << 20: 1}}


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout


def first_line(cmd):
    return (sh(cmd).strip().splitlines() or [""])[0]


def build():
    """The variants: name -> (language, layout, label, command, rounds key)."""
    os.makedirs(OUT, exist_ok=True)
    myla = os.path.join(REPO, "build", "myla")
    variants = {}
    for layout in ("split", "complex"):
        exe = os.path.join(OUT, f"myla_{layout}")
        sh([myla, "build", os.path.join(HERE, f"fft_{layout}.my"), "-o", exe])
        variants[f"myla_{layout}"] = ("Myla", layout, "Myla", [exe], "native")
        define = ["-DCOMPLEX"] if layout == "complex" else []
        for opt, flags in (("O2", ["-O2"]), ("O3", ["-O3", "-march=native"])):
            exe = os.path.join(OUT, f"c_{layout}_{opt}")
            sh(["gcc", *flags, "-ffp-contract=off", *define, os.path.join(HERE, "fft.c"), "-o", exe, "-lm"])
            label = "C, gcc -O2" if opt == "O2" else "C, gcc -O3 -march=native"
            variants[f"c_{layout}_{opt}"] = ("C", layout, label, [exe], "native")
    cs = os.path.join(OUT, "csharp")
    shutil.rmtree(cs, ignore_errors=True)
    shutil.copytree(os.path.join(HERE, "csharp"), cs, ignore=shutil.ignore_patterns("out", "obj", "bin"))
    sh(["dotnet", "build", "-c", "Release", "-o", "out", "Program.cs"], cwd=cs)
    for layout in ("split", "complex"):
        variants[f"csharp_{layout}"] = ("C#", layout, "C#, .NET", ["dotnet", os.path.join(cs, "out", "Program.dll"), layout], "native")
        variants[f"python_{layout}"] = ("Python", layout, "Python, CPython", [sys.executable, os.path.join(HERE, "fft.py"), layout], "python")
    return variants


def run(cmd, n, rounds, pin):
    """(checksum, error, seconds) of one run."""
    out = sh([*pin, *cmd, str(n), str(rounds)]).split()
    assert out[0] == f"fft-{n}" and int(out[3]) == rounds, out
    return int(out[1]), int(out[2]), float(out[4])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--json")
    opts = ap.parse_args()

    variants = build()
    cpus = sorted(os.sched_getaffinity(0))
    pin = ["taskset", "-c", str(cpus[-1])] if shutil.which("taskset") and len(cpus) > 1 else []

    answers = {}
    for n, rounds in CHECKS:
        got = {name: run(v[3], n, rounds, pin)[:2] for name, v in variants.items()}
        if len(set(got.values())) != 1:
            sys.exit(f"MISMATCH at {n} points, {rounds} rounds: {got}")
        answers[f"{n}x{rounds}"] = list(next(iter(got.values())))
        print(f"check {n:>8} points, {rounds} round trips: all {len(got)} variants print {answers[f'{n}x{rounds}']}")

    results = []
    checksums = {}
    for name, (language, layout, label, cmd, key) in variants.items():
        entry = {"name": name, "language": language, "layout": layout, "label": label, "sizes": {}}
        for n in SIZES:
            rounds = ROUNDS[key][n]
            runs = [run(cmd, n, rounds, pin) for _ in range(opts.runs)]
            checksums.setdefault(n, set()).update(r[0] for r in runs)
            secs = [r[2] for r in runs]
            butterflies = rounds * 2 * (n // 2) * (n.bit_length() - 1)
            entry["sizes"][str(n)] = {
                "rounds": rounds, "seconds": secs, "median": statistics.median(secs),
                "ns_per_butterfly": statistics.median(secs) * 1e9 / butterflies,
                "ns_min": min(secs) * 1e9 / butterflies, "ns_max": max(secs) * 1e9 / butterflies,
            }
            print(f"{name:<16} {n:>8} points  {rounds:>5} round trips  median {statistics.median(secs):8.3f} s"
                  f"  {entry['sizes'][str(n)]['ns_per_butterfly']:8.2f} ns/butterfly")
        results.append(entry)
    for n, sums in checksums.items():
        if len(sums) != 1:
            sys.exit(f"MISMATCH of the checksum at {n} points: {sums}")
        answers[f"{n}"] = [next(iter(sums))]

    data = {
        "date": datetime.date.today().isoformat(),
        "commit": first_line(["git", "-C", REPO, "rev-parse", "--short", "HEAD"]),
        "machine": {
            "cpu": next((l.split(": ", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), platform.processor()),
            "cpus": os.cpu_count(), "kernel": platform.release(), "pinned": bool(pin),
        },
        "versions": {
            "Myla": "commit " + first_line(["git", "-C", REPO, "rev-parse", "--short", "HEAD"]),
            "C": first_line(["gcc", "--version"]),
            "C#": ".NET SDK " + first_line(["dotnet", "--version"]),
            "Python": "CPython " + platform.python_version(),
        },
        "runs": opts.runs, "checks": answers, "variants": results,
    }
    if opts.json:
        with open(opts.json, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        print("wrote", opts.json)


if __name__ == "__main__":
    main()
