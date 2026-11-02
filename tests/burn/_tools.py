"""The Myla tools the burn tests run (`selfhost/<name>.my`, `tools/…`), and the
compiler that builds them and the test programs (MYLA-58, MYLA-235).

The self-hosted compiler builds them, bootstrapped as `scripts/bootstrap.sh`
does: the seed (`bootstrap/seed.s`, MYLA-218) assembled is stage 0, it compiles
the compiler (stage 1), stage 1 compiles it again, and that stage (at the fixed
point the same as `build/stage3`) compiles every tool. (The Python backend, the
fallback until MYLA-219, is gone.)

Each binary is built once per content hash of the standard library,
`selfhost/`, `tools/` and the seed, into `build/test-tools/` (gitignored),
and reused by every test module and every later run until one of those
sources changes.
"""
from __future__ import annotations

import functools
import glob
import hashlib
import os
import subprocess

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_CACHE = os.path.join(_REPO, "build", "test-tools")

# the folder holding the standard library (`std/`) and `debug/myla_gdb.py`
STDLIB_ROOT = os.path.join(_REPO, "lib")
BACKEND = "selfhost"


@functools.cache
def _sources_hash() -> str:
    files = sorted(
        glob.glob(os.path.join(STDLIB_ROOT, "std", "*.my"))
        + glob.glob(os.path.join(_REPO, "selfhost", "*.my"))
        + glob.glob(os.path.join(_REPO, "tools", "**", "*.my"), recursive=True)
        + [os.path.join(_REPO, "bootstrap", "seed.s")]
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


def _assemble(asm: str, out: str) -> None:
    """The assembly file `asm` assembled and linked into `out`."""
    subprocess.run(["as", "--64", "-o", out + ".o", asm], check=True)
    subprocess.run(["ld", "-o", out, out + ".o"], check=True)


def _compile_with(compiler: str, relpath: str, out: str) -> None:
    """`relpath` compiled by a stage of the self-hosted compiler, assembled and
    linked into `out`."""
    with open(out + ".s", "wb") as fh:
        subprocess.run([compiler, relpath, STDLIB_ROOT], cwd=_REPO, stdout=fh, check=True)
    _assemble(out + ".s", out)


@functools.cache
def native_compiler() -> str:
    """The self-hosted compiler of the current sources, bootstrapped from the
    seed and cached."""
    seed = os.path.join(_REPO, "bootstrap", "seed.s")
    stage0 = _cached("stage0", lambda out: _assemble(seed, out))
    stage1 = _cached("stage1", lambda out: _compile_with(stage0, "selfhost/gen_main.my", out))
    return _cached("stage2", lambda out: _compile_with(stage1, "selfhost/gen_main.my", out))


def selfhost_tool(name: str) -> str:
    """The path of `selfhost/<name>.my` built natively (cached)."""
    return myla_tool(f"selfhost/{name}.my", name)


def myla_tool(relpath: str, name: str) -> str:
    """The path of the Myla program `relpath` (from the repository root) built
    natively by the self-hosted compiler, cached under `name`."""
    compiler = native_compiler()
    return _cached(name, lambda out: _compile_with(compiler, relpath, out))
