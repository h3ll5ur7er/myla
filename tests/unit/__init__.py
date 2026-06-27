"""Ensure the project's ``src/`` directory is importable during test discovery.

This runs when unittest imports the ``unit`` package, before any test module is
loaded. Inserting ``src`` at the front of ``sys.path`` also makes the ``myla``
package take precedence over the root ``myla.py`` entry-point shim (which would
otherwise shadow it when the repo root is on ``sys.path``).
"""
import os
import sys

_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")
)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
