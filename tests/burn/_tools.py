"""The Myla tools the burn tests run (`selfhost/<name>.my`, `tools/…`), built by
the Python backend and cached (MYLA-58).

A tool is built once per content hash of the Python toolchain, the standard
library, `selfhost/` and `tools/`, into `build/test-tools/` (gitignored), and
reused by every test module and every later run until one of those sources
changes.
"""
from __future__ import annotations

import functools
import glob
import hashlib
import os

from myla.compiler import build
from myla.loader import default_stdlib_root, link
from myla.types import check

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_CACHE = os.path.join(_REPO, "build", "test-tools")


@functools.cache
def _sources_hash() -> str:
    files = sorted(
        glob.glob(os.path.join(_REPO, "src", "myla", "**", "*.py"), recursive=True)
        + glob.glob(os.path.join(_REPO, "src", "myla", "std", "*.my"))
        + glob.glob(os.path.join(_REPO, "selfhost", "*.my"))
        + glob.glob(os.path.join(_REPO, "tools", "**", "*.my"), recursive=True)
    )
    h = hashlib.sha256()
    for path in files:
        h.update(os.path.relpath(path, _REPO).encode())
        with open(path, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:16]


def selfhost_tool(name: str) -> str:
    """The path of `selfhost/<name>.my` built natively (cached)."""
    return myla_tool(f"selfhost/{name}.my", name)


def myla_tool(relpath: str, name: str) -> str:
    """The path of the Myla program `relpath` (from the repository root) built
    natively, cached under `name`; built if the cache has no binary for the
    current sources."""
    path = os.path.join(_CACHE, f"{name}-{_sources_hash()}")
    if not os.path.exists(path):
        os.makedirs(_CACHE, exist_ok=True)
        for stale in glob.glob(os.path.join(_CACHE, f"{name}-*")):
            os.remove(stale)
        tmp = f"{path}.{os.getpid()}.tmp"
        source = os.path.join(_REPO, relpath)
        try:
            build(check(link(source, stdlib_root=default_stdlib_root())), tmp)
            os.replace(tmp, path)   # atomic, so parallel runs never see half a file
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return path
