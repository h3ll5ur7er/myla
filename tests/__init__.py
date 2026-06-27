"""Test package bootstrap.

Adds the project's ``src/`` directory to ``sys.path`` so the ``myla`` package is
importable when the suite is run straight from the repo root with no install:

    python3 -m unittest discover -s tests
    uv run python -m unittest discover -s tests
"""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
