#!/usr/bin/env python3
"""Benchmarks: the gap to C (MYLA-242).

    python3 benchmarks/run.py [name ...] [--runs N] [--no-callgrind] [--json FILE]
                              [--compare FILE]

Each benchmark is a directory under benchmarks/ with `<name>.my`, `<name>.c`
(idiomatic C), `<name>_myla.c` (C with Myla's semantics, myla_rt.h) and
`bench.json` (`size` for the timing, `profile_size` for callgrind,
`test_size` for tests/burn/test_benchmarks.py). It builds five versions:

    myla           the Myla program, `build/myla build`
    c              idiomatic C, gcc -O2
    c_myla_gcc     C with Myla's semantics, gcc -O2
    c_myla_clang   the same, clang -O2 (LLVM's optimizer on the same semantics)
    c_myla_O0      the same, gcc -O0 (an unoptimizing compiler)

checks that they print the same, and measures each: wall time (the median
of --runs runs at `size`), peak memory, binary size, and the instructions
callgrind counts at `profile_size` (exact, so a noisy machine doesn't
matter). For the Myla version it also lists the functions the instructions
went to. All C is compiled with -fwrapv (Myla's integers wrap) and linked
with -lm.

`--json FILE` saves the results with the date, the commit and the machine;
`--compare FILE` adds, for the Myla version, its change against such a file
(benchmarks/results/ keeps the baseline, MYLA-242).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "build", "bench")

VARIANTS = ["myla", "c", "c_myla_gcc", "c_myla_clang", "c_myla_O0"]
LABELS = {
    "myla": "Myla",
    "c": "C, gcc -O2",
    "c_myla_gcc": "C + Myla semantics, gcc -O2",
    "c_myla_clang": "C + Myla semantics, clang -O2",
    "c_myla_O0": "C + Myla semantics, gcc -O0",
}


def benchmarks() -> list[str]:
    return sorted(d for d in os.listdir(HERE) if os.path.isfile(os.path.join(HERE, d, "bench.json")))


def config(name: str) -> dict:
    with open(os.path.join(HERE, name, "bench.json"), encoding="utf-8") as fh:
        return json.load(fh)


def build(name: str, variant: str, myla: str) -> str | None:
    """The binary of `variant`, built into build/bench/; None when its
    compiler is missing."""
    src = os.path.join(HERE, name)
    exe = os.path.join(OUT, f"{name}.{variant}")
    os.makedirs(OUT, exist_ok=True)
    if variant == "myla":
        cmd = [myla, "build", os.path.join(src, f"{name}.my"), "-o", exe]
    else:
        cc, opt = {"c": ("gcc", "-O2"), "c_myla_gcc": ("gcc", "-O2"), "c_myla_clang": ("clang", "-O2"),
                   "c_myla_O0": ("gcc", "-O0")}[variant]
        if shutil.which(cc) is None:
            return None
        file = f"{name}.c" if variant == "c" else f"{name}_myla.c"
        cmd = [cc, opt, "-fwrapv", "-o", exe, os.path.join(src, file), "-lm"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"building {name} ({variant}) failed:\n{proc.stdout}{proc.stderr}")
    return exe


def run_once(exe: str, size: int) -> tuple[str, float, object]:
    """Output, wall seconds and resource usage of one run."""
    with tempfile.TemporaryFile() as out:
        start = time.perf_counter()
        proc = subprocess.Popen([exe, str(size)], stdout=out, stderr=subprocess.PIPE)
        _, status, usage = os.wait4(proc.pid, 0)
        wall = time.perf_counter() - start
        proc.returncode = os.waitstatus_to_exitcode(status)
        err = proc.stderr.read().decode()
        proc.stderr.close()
        if proc.returncode != 0:
            raise SystemExit(f"{exe} {size} failed ({proc.returncode}): {err}")
        out.seek(0)
        return out.read().decode(), wall, usage


def symbols(exe: str) -> list[tuple[int, str]]:
    """The binary's symbols by address. Myla's labels have no symbol type, so
    valgrind shows their addresses only."""
    proc = subprocess.run(["nm", "-n", exe], capture_output=True, text=True)
    out = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] in "tT":
            out.append((int(parts[0], 16), parts[2]))
    return out


def name_of(where: str, syms: list[tuple[int, str]]) -> str:
    """A function as callgrind_annotate names it, an address made a symbol."""
    m = re.match(r"0x([0-9a-f]+)('\d+)?$", where)
    if not m:
        return where
    addr = int(m.group(1), 16)
    best = where
    for a, name in syms:
        if a > addr:
            break
        best = name if a == addr else f"{name}+{addr - a:#x}"
    return best


def callgrind(exe: str, size: int, top: int) -> tuple[int, list[tuple[int, str]]]:
    """Instructions of a run at `size`, and the `top` functions they went to
    (instructions spent in the function itself)."""
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "callgrind.out")
        proc = subprocess.run(["valgrind", "--tool=callgrind", f"--callgrind-out-file={data}", exe, str(size)],
                              capture_output=True, text=True)
        m = re.search(r"Collected : (\d+)", proc.stderr)
        if proc.returncode != 0 or not m:
            raise SystemExit(f"callgrind on {exe} failed:\n{proc.stderr[-2000:]}")
        total = int(m.group(1))
        functions: list[tuple[int, str]] = []
        syms = symbols(exe)
        if top:
            ann = subprocess.run(["callgrind_annotate", "--threshold=100", data], capture_output=True, text=True)
            for line in ann.stdout.splitlines():
                f = re.match(r"\s*([\d,]+)\s+\([\d.]+%\)\s+(.*)$", line)
                if f and "PROGRAM TOTALS" not in line and ":" in f.group(2):
                    where = f.group(2).split(" [")[0]
                    functions.append((int(f.group(1).replace(",", "")), name_of(where.split(":", 1)[1], syms)))
            functions = functions[:top]
        return total, functions


def measure(name: str, myla: str, runs: int, use_callgrind: bool, top: int) -> dict:
    cfg = config(name)
    result = {"name": name, "measures": cfg.get("measures", ""), "size": cfg["size"],
              "profile_size": cfg["profile_size"], "variants": {}}
    reference = None
    for variant in VARIANTS:
        exe = build(name, variant, myla)
        if exe is None:
            continue
        outputs, walls, users, systems, faults, rss = set(), [], [], [], [], 0
        for _ in range(runs):
            out, wall, usage = run_once(exe, cfg["size"])
            outputs.add(out)
            walls.append(wall)
            users.append(usage.ru_utime)
            systems.append(usage.ru_stime)
            faults.append(usage.ru_minflt)
            rss = max(rss, usage.ru_maxrss)
        out = outputs.pop()
        if outputs:
            raise SystemExit(f"{name} ({variant}) printed different things on different runs")
        if reference is None:
            reference = out
        elif out != reference:
            raise SystemExit(f"{name}: {variant} printed\n{out}\nbut Myla printed\n{reference}")
        entry = {"seconds": statistics.median(walls), "user_seconds": statistics.median(users),
                 "system_seconds": statistics.median(systems), "page_faults": int(statistics.median(faults)),
                 "max_rss_kb": rss, "binary_bytes": os.path.getsize(exe)}
        if use_callgrind:
            entry["instructions"], functions = callgrind(exe, cfg["profile_size"], top if variant == "myla" else 0)
            if variant == "myla":
                entry["top_functions"] = functions
        result["variants"][variant] = entry
        print(f"  {name:14} {LABELS[variant]:32} {entry['seconds'] * 1000:9.1f} ms", file=sys.stderr)
    return result


def machine() -> dict:
    """What the timings depend on: the processor and the cores."""
    model = ""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    return {"cpu": model, "cores": os.cpu_count()}


def commit() -> str:
    proc = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return proc.stdout.strip()


def load_results(path: str) -> dict[str, dict]:
    """The results saved by --json, by benchmark name."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    results = data["results"] if isinstance(data, dict) else data
    return {r["name"]: r for r in results}


def table(results: list[dict], baseline: dict[str, dict] | None = None) -> str:
    lines = []
    for r in results:
        v = r["variants"]
        lines.append(f"### {r['name']}\n\n{r['measures']}; size {r['size']}, instructions at {r['profile_size']}.\n")
        lines.append("| Version | Time | × Myla | User | System | Page faults | Instructions | × Myla | Peak memory | Binary |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        base = v["myla"]
        for variant in VARIANTS:
            if variant not in v:
                continue
            e = v[variant]
            t_ratio = e["seconds"] / base["seconds"]
            ins = e.get("instructions")
            ins_txt = f"{ins:,}" if ins else "–"
            ins_ratio = f"{ins / base['instructions']:.2f}" if ins and base.get("instructions") else "–"
            lines.append(f"| {LABELS[variant]} | {e['seconds'] * 1000:.0f} ms | {t_ratio:.2f} "
                         f"| {e['user_seconds'] * 1000:.0f} ms | {e['system_seconds'] * 1000:.0f} ms | {e['page_faults']:,} "
                         f"| {ins_txt} | {ins_ratio} "
                         f"| {e['max_rss_kb'] / 1024:.1f} MB | {e['binary_bytes'] / 1024:.0f} KB |")
        before = (baseline or {}).get(r["name"], {}).get("variants", {}).get("myla")
        if before:
            parts = [f"time {before['seconds'] * 1000:.0f} → {base['seconds'] * 1000:.0f} ms "
                     f"({before['seconds'] / base['seconds']:.2f}× as fast)"]
            if before.get("instructions") and base.get("instructions"):
                parts.append(f"instructions {before['instructions'] / base['instructions']:.2f}× fewer")
            parts.append(f"peak memory {before['max_rss_kb'] / 1024:.0f} → {base['max_rss_kb'] / 1024:.0f} MB")
            lines.append("\nAgainst the baseline: " + ", ".join(parts) + ".")
        top = base.get("top_functions")
        if top:
            total = base["instructions"]
            lines.append("\nWhere Myla's instructions go (in the function itself):\n")
            for count, fn in top:
                lines.append(f"- `{fn}`: {100 * count / total:.1f} %")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="benchmarks to run (default: all)")
    ap.add_argument("--runs", type=int, default=5, help="timed runs per version (default 5)")
    ap.add_argument("--no-callgrind", action="store_true", help="skip counting instructions")
    ap.add_argument("--top", type=int, default=8, help="functions to list for the Myla version")
    ap.add_argument("--json", help="also write the results to this file")
    ap.add_argument("--compare", help="results saved by --json to compare the Myla version with")
    ap.add_argument("--myla", default=os.path.join(REPO, "build", "myla"), help="the myla CLI")
    args = ap.parse_args()
    names = args.names or benchmarks()
    use_callgrind = not args.no_callgrind and shutil.which("valgrind") is not None
    results = [measure(n, args.myla, args.runs, use_callgrind, args.top) for n in names]
    baseline = load_results(args.compare) if args.compare else None
    print(table(results, baseline))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"date": time.strftime("%Y-%m-%d"), "commit": commit(), "machine": machine(),
                       "results": results}, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
