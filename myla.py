#!/usr/bin/env python3
"""Myla bootstrapping toolchain entry point.

Usage:
    uv run myla.py <command> [args]
    python3 myla.py <command> [args]

See `myla.py --help` for the available commands. The real implementation lives
in the `myla` package under `src/`; this shim just makes it importable when run
directly from the repo root without installing anything (honoring the
no-dependencies vision).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from myla.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
