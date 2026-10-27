#!/usr/bin/env python3
"""Collect the programs the Python unit tests expect to fail type checking.

Runs tests/unit with `myla.lexer.tokenize` and `myla.types.check` wrapped:
every source whose check raises a TypeCheckError is recorded. The result,
tests/burn/data/type_error_snippets.json, is the snippet corpus of the
self-hosted checker gate (tests/burn/test_selfhost_checker.py), which compares
the self-hosted checker's message and position with Python's on each (MYLA-28).

    python3 scripts/harvest_type_errors.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
OUT = os.path.join(REPO, "tests", "burn", "data", "type_error_snippets.json")
sys.path.insert(0, REPO)                       # for the `tests` package
sys.path.insert(0, os.path.join(REPO, "src"))  # ahead of the repo's myla.py

import myla.lexer  # noqa: E402
import myla.types  # noqa: E402
from myla.errors import TypeCheckError  # noqa: E402

_last_source: list[str] = []
_found: list[str] = []
_tokenize = myla.lexer.tokenize
_check = myla.types.check


def tokenize(source: str, *args, **kwargs):
    _last_source[:] = [source]
    return _tokenize(source, *args, **kwargs)


def check(program, *args, **kwargs):
    # taken on entry: `check` tokenizes the prelude itself
    source = _last_source[0] if _last_source else None
    try:
        return _check(program, *args, **kwargs)
    except TypeCheckError:
        if source is not None and source not in _found and "import" not in source:
            _found.append(source)
        raise


def _fails(source: str) -> bool:
    """Whether `source` fails to type-check on its own (some tests check
    differently, e.g. without the prelude)."""
    from myla.parser import parse
    try:
        _check(parse(_tokenize(source)))
    except TypeCheckError:
        return True
    return False


def main() -> int:
    # Patch before the test modules import the names.
    myla.lexer.tokenize = tokenize
    myla.types.check = check
    suite = unittest.defaultTestLoader.discover(os.path.join(REPO, "tests", "unit"), top_level_dir=REPO)
    unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    found = [src for src in _found if _fails(src)]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(found, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"{len(found)} snippets -> {os.path.relpath(OUT, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
