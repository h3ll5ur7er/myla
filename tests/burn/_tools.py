"""The Myla tools the burn tests run (`selfhost/<name>.my`, `tools/…`), and the
compiler that builds them and the test programs (MYLA-58, MYLA-235).

The self-hosted compiler builds them: the Python backend builds stage 1 of the
bootstrap (`selfhost/gen_main.my`), stage 1 compiles the compiler again, and
that stage (at the fixed point the same as `build/stage3`) compiles every tool,
as `scripts/bootstrap.sh` does. `MYLA_TEST_BACKEND=python` makes the Python
backend build them all instead: the fallback.

Each binary is built once per content hash of the Python toolchain, the
standard library, `selfhost/` and `tools/`, into `build/test-tools/`
(gitignored), and reused by every test module and every later run until one
of those sources changes.
"""
from __future__ import annotations

import functools
import glob
import hashlib
import os
import subprocess

from myla.compiler import build
from myla.loader import default_stdlib_root, link
from myla.types import check

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_CACHE = os.path.join(_REPO, "build", "test-tools")

# "selfhost" (the default) or "python" (the fallback)
BACKEND = os.environ.get("MYLA_TEST_BACKEND", "selfhost")


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


def _cached(name: str, make) -> str:
    """The cached binary `name` for the current sources, made by `make(path)`
    if the cache has none."""
    path = os.path.join(_CACHE, f"{name}-{BACKEND}-{_sources_hash()}")
    if not os.path.exists(path):
        os.makedirs(_CACHE, exist_ok=True)
        for stale in glob.glob(os.path.join(_CACHE, f"{name}-{BACKEND}-*")):
            os.remove(stale)
        tmp = f"{path}.{os.getpid()}.tmp"
        try:
            make(tmp)
            os.replace(tmp, path)   # atomic, so parallel runs never see half a file
        finally:
            for leftover in (tmp, tmp + ".s", tmp + ".o"):
                if os.path.exists(leftover):
                    os.remove(leftover)
    return path


def _python_build(relpath: str, out: str) -> None:
    build(check(link(os.path.join(_REPO, relpath), stdlib_root=default_stdlib_root())), out)


def _compile_with(compiler: str, relpath: str, out: str) -> None:
    """`relpath` compiled by a stage of the self-hosted compiler, assembled and
    linked into `out`."""
    with open(out + ".s", "wb") as fh:
        subprocess.run([compiler, relpath, default_stdlib_root()], cwd=_REPO, stdout=fh, check=True)
    subprocess.run(["as", "--64", "-o", out + ".o", out + ".s"], check=True)
    subprocess.run(["ld", "-o", out, out + ".o"], check=True)


@functools.cache
def native_compiler() -> str | None:
    """The self-hosted compiler of the current sources, bootstrapped and
    cached; None with the Python fallback."""
    if BACKEND == "python":
        return None
    stage1 = _cached("stage1", lambda out: _python_build("selfhost/gen_main.my", out))
    return _cached("stage2", lambda out: _compile_with(stage1, "selfhost/gen_main.my", out))


def selfhost_tool(name: str) -> str:
    """The path of `selfhost/<name>.my` built natively (cached)."""
    return myla_tool(f"selfhost/{name}.my", name)


def myla_tool(relpath: str, name: str) -> str:
    """The path of the Myla program `relpath` (from the repository root) built
    natively by the self-hosted compiler (the Python backend with the
    fallback), cached under `name`."""
    compiler = native_compiler()
    if compiler is None:
        return _cached(name, lambda out: _python_build(relpath, out))
    return _cached(name, lambda out: _compile_with(compiler, relpath, out))
