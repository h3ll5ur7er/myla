#!/usr/bin/env python3
"""Turns a benchLANG results file into the JSON the report page embeds.

    python3 report_data.py benchmark_results_<stamp>.txt > results.json
    python3 report_data.py benchmark_results_<stamp>.txt --into report.html

`--into` writes the JSON into the page's `<script id="data">` block instead.
`--compile FILE`, after the results file, takes the compile times from a
`./run_benchmarks.sh --compile-only` results file (a pass with warm caches).
"""
import datetime
import json
import os
import re
import sys

WORKLOADS = ["primes", "fib", "strings", "mandelbrot", "binarytrees", "knucleotide"]
SHORT = {
    "JavaScript (Bun)": "JS (Bun)", "JavaScript (Node)": "JS (Node)",
    "Python (PyPy3)": "Python (PyPy)", "Python (Python3)": "Python (CPython)",
}


def parse(path):
    meta, langs = {}, {}
    stamp = re.search(r"(\d{4}-?\d{2}-?\d{2})", os.path.basename(path))
    if stamp:
        day = datetime.datetime.strptime(stamp.group(1).replace("-", ""), "%Y%m%d")
        meta["date"] = f"{day.day} {day:%b %Y}"
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("# ") and ": " in line:
            key, value = line[2:].split(": ", 1)
            meta[key] = value
            continue
        f = line.split("\t")
        if f[0] == "LANG":
            langs[f[1]] = {
                "name": SHORT.get(f[1], f[1]), "version": f[2],
                "binary": int(f[3]) if f[3] else None,
                "compile": float(f[4]) if f[4] and f[3] else None,
                "times": {w: [] for w in WORKLOADS}, "checksums": {}, "wall": [], "cpu": [], "rss": 0,
            }
        elif f[0] == "RESULT":
            langs[f[1]]["times"][f[3]].append(float(f[5]))
            langs[f[1]]["checksums"][f[3]] = f[4]
        elif f[0] == "RUSAGE":
            lang = langs[f[1]]
            lang["wall"].append(float(f[3]))
            lang["cpu"].append(float(f[4]) + float(f[5]))
            lang["rss"] = max(lang["rss"], int(f[6]))
    out = []
    for lang in langs.values():
        if not lang["wall"] or any(not lang["times"][w] for w in WORKLOADS):
            continue
        times = {w: round(sum(v) / len(v), 4) for w, v in lang["times"].items()}
        spread = {w: [min(v), max(v)] for w, v in lang["times"].items()}
        out.append({
            "name": lang["name"], "version": lang["version"], "binary": lang["binary"],
            "compile": lang["compile"], "rss": lang["rss"], "runs": len(lang["wall"]),
            "wall": round(sum(lang["wall"]) / len(lang["wall"]), 3),
            "cpu": round(sum(lang["cpu"]) / len(lang["cpu"]), 3),
            "times": times, "spread": spread, "total": round(sum(times.values()), 4),
            "checksums": lang["checksums"],
        })
    out.sort(key=lambda l: l["total"])
    sums = {w: sorted({l["checksums"][w] for l in out}) for w in WORKLOADS}
    return {"meta": meta, "workloads": WORKLOADS, "checksums": sums, "langs": out}


def compile_times(path):
    """The compile seconds of a `--compile-only` results file, by language."""
    out = {}
    for line in open(path, encoding="utf-8"):
        f = line.rstrip("\n").split("\t")
        if f[0] == "LANG" and f[4]:
            out[SHORT.get(f[1], f[1])] = float(f[4])
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    data = parse(args.pop(0))
    if "--compile" in args:
        i = args.index("--compile")
        times = compile_times(args[i + 1])
        del args[i:i + 2]
        for lang in data["langs"]:
            if lang["compile"] is not None:
                lang["compile"] = times[lang["name"]]
    if len(args) == 2 and args[0] == "--into":
        page = open(args[1], encoding="utf-8").read()
        block = re.compile(r'(<script id="data" type="application/json">).*?(</script>)', re.S)
        text = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
        page, n = block.subn(lambda m: m.group(1) + text + m.group(2), page, count=1)
        if n != 1:
            sys.exit("no data block in " + args[1])
        open(args[1], "w", encoding="utf-8").write(page)
    else:
        json.dump(data, sys.stdout, indent=1)
