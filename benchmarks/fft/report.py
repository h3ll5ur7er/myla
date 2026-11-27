#!/usr/bin/env python3
"""Writes a results file of run.py and the benchmark's sources into report.html (MYLA-975).

    python3 benchmarks/fft/report.py benchmarks/fft/results-<date>.json

The page keeps both in `<script type="application/json">` blocks, `results`
and `sources-data`; this replaces their contents.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = [
    ("fft_split.my", "Myla, two lists of floats"),
    ("fft_complex.my", "Myla, a list of a Complex struct"),
    ("fft.c", "C, both layouts (-DCOMPLEX for the structs)"),
    ("csharp/Program.cs", "C#, both layouts"),
    ("fft.py", "Python, both layouts"),
    ("run.py", "The runner: builds, checks the answers, times"),
    ("report.py", "This page's data: results and sources written into it"),
]


def fill(page, block, value):
    pattern = re.compile(r'(<script id="%s" type="application/json">).*?(</script>)' % block, re.S)
    text = json.dumps(value, separators=(",", ":")).replace("</", "<\\/")
    page, n = pattern.subn(lambda m: m.group(1) + text + m.group(2), page, count=1)
    if n != 1:
        sys.exit(f"no {block} block in report.html")
    return page


def main():
    with open(sys.argv[1], encoding="utf-8") as fh:
        results = json.load(fh)
    sources = []
    for path, what in SOURCES:
        with open(os.path.join(HERE, path), encoding="utf-8") as fh:
            sources.append({"path": "benchmarks/fft/" + path, "what": what, "text": fh.read()})
    target = os.path.join(HERE, "report.html")
    with open(target, encoding="utf-8") as fh:
        page = fh.read()
    page = fill(fill(page, "results", results), "sources-data", sources)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(page)


if __name__ == "__main__":
    main()
