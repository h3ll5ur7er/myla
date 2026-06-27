"""Ensure the project's ``src/`` directory is importable during test discovery.

See tests/unit/__init__.py for the rationale.
"""
import os
import sys

_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")
)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
