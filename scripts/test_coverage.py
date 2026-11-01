#!/usr/bin/env python3
"""test_coverage.py: the share of value-returning functions with `#test`
cases, per module of `selfhost/` and overall (D109, MYLA-184).

    scripts/test_coverage.py [DIR]     # default: selfhost

Counts free functions and methods that return a value; a function counts as
tested when it carries at least one `#test` case. The target is 80 %, softly
enforced: `tests/burn/test_selfhost_coverage.py` warns below it.
"""

from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

from myla import ast                    # noqa: E402
from myla.lexer import tokenize         # noqa: E402
from myla.parser import parse           # noqa: E402

TARGET = 0.80


def module_counts(path: str) -> tuple[int, int]:
    """(tested, value-returning functions) of one source file."""
    with open(path, encoding="utf-8") as fh:
        program = parse(tokenize(fh.read()))
    funs: list[ast.FunDecl] = []
    for d in program.decls:
        if isinstance(d, ast.FunDecl):
            funs.append(d)
        elif isinstance(d, ast.ImplDecl):
            funs.extend(d.methods)
    returning = [f for f in funs if f.ret_type is not None and f.body is not None]
    tested = [f for f in returning if any(a.name == "test" for a in f.attributes)]
    return len(tested), len(returning)


def coverage(directory: str) -> list[tuple[str, int, int]]:
    """(file name, tested, value-returning) per `.my` file, sorted by name."""
    out = []
    for name in sorted(os.listdir(directory)):
        if name.endswith(".my"):
            tested, total = module_counts(os.path.join(directory, name))
            out.append((name, tested, total))
    return out


def report(rows: list[tuple[str, int, int]]) -> str:
    lines = [f"{'module':24} {'tested':>7} {'of':>6} {'share':>7}"]
    for name, tested, total in rows:
        share = f"{100 * tested / total:.0f} %" if total else "-"
        lines.append(f"{name:24} {tested:7} {total:6} {share:>7}")
    tested = sum(r[1] for r in rows)
    total = sum(r[2] for r in rows)
    lines.append(f"{'overall':24} {tested:7} {total:6} {100 * tested / max(total, 1):5.0f} %")
    return "\n".join(lines)


def overall(rows: list[tuple[str, int, int]]) -> float:
    total = sum(r[2] for r in rows)
    return sum(r[1] for r in rows) / total if total else 1.0


def main() -> int:
    directory = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "selfhost")
    rows = coverage(directory)
    print(report(rows))
    share = overall(rows)
    if share < TARGET:
        print(f"below the target of {TARGET:.0%} (D109)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
