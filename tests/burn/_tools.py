"""The Myla tools the burn tests run (`selfhost/<name>.my`, `tools/…`), and the
compiler that builds them and the test programs (MYLA-58, MYLA-235).

The self-hosted compiler builds them, bootstrapped as `scripts/bootstrap.sh`
does: the machine's seed (`bootstrap/seed.s` on x86-64,
`bootstrap/seed-aarch64.s` on aarch64, MYLA-218) assembled is stage 0, it compiles
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
import platform
import subprocess
import sys

try:
    import fcntl
except ImportError:          # Windows (MYLA-926 step 2): msvcrt's lock instead
    fcntl = None
    import msvcrt

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_CACHE = os.path.join(_REPO, "build", "test-tools")

# The machine the tools are built for, as scripts/host.sh tells it: x86-64 or
# aarch64 Linux, or x86-64 Windows (MYLA-926: the burn suites run natively on
# aarch64 and Windows runners), its seed, and its programs' suffix.
WINDOWS = sys.platform == "win32"
_SEED = os.path.join(_REPO, "bootstrap", "seed-windows.s" if WINDOWS
                     else "seed-aarch64.s" if platform.machine() == "aarch64" else "seed.s")
EXE = ".exe" if WINDOWS else ""

# the folder holding the standard library (`std/`) and `debug/myla_gdb.py`
STDLIB_ROOT = os.path.join(_REPO, "lib")
BACKEND = "selfhost"


@functools.cache
def _sources_hash() -> str:
    files = sorted(
        glob.glob(os.path.join(STDLIB_ROOT, "std", "*.my"))
        + glob.glob(os.path.join(_REPO, "selfhost", "*.my"))
        + glob.glob(os.path.join(_REPO, "tools", "**", "*.my"), recursive=True)
        + [_SEED]
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
    path = os.path.join(_CACHE, f"{name}-{BACKEND}-{_sources_hash()}{EXE}")
    if os.path.exists(path):
        return path
    os.makedirs(_CACHE, exist_ok=True)
    # one process at a time makes `name` (scripts/test-target.py runs suites
    # in parallel, MYLA-268): the others wait, then find it made; the stale
    # copies, and nothing another process is still making, go under the lock
    with open(os.path.join(_CACHE, f"{name}-{BACKEND}.lock"), "w") as lock:
        _lock(lock)
        if os.path.exists(path):
            return path
        for stale in glob.glob(os.path.join(_CACHE, f"{name}-{BACKEND}-*")):
            os.remove(stale)
        tmp = f"{path}.{os.getpid()}.tmp{EXE}"
        try:
            make(tmp)
            os.replace(tmp, path)   # atomic, so a run without the lock never sees half a file
        finally:
            for leftover in glob.glob(glob.escape(tmp) + "*"):
                if os.path.exists(leftover):
                    os.remove(leftover)
    return path


def _lock(fh) -> None:
    """`fh`'s file locked for this process, waiting for another's lock."""
    if fcntl is not None:
        fcntl.flock(fh, fcntl.LOCK_EX)
        return
    while True:
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            return
        except OSError:       # LK_LOCK gives up after ten seconds: wait on
            continue


def windows_imports(asm: str) -> list[tuple[str, list[str]]]:
    """The system DLLs the Windows assembly `asm` calls into, each with the
    functions it calls of it through their import slots: the lists its import
    libraries are made from (D211, D212), as the code generator names them at
    the assembly's end (`# import <dll> <function> ...`, its `windows_dlls`,
    MYLA-722)."""
    out = []
    for line in asm.splitlines():
        if line.startswith("# import "):
            words = line.split()
            out.append((words[2], words[3:]))
    return out


def link_windows(asm_path: str, out: str, quiet: bool = True) -> None:
    """The Windows assembly `asm_path` made the `.exe` `out` as `myla build
    --target x86_64-windows` makes it (D211, scripts/host.sh's
    windows_asm_to_bin): clang assembles it, llvm-dlltool makes an import
    library of each system DLL it calls, lld-link links them all."""
    run = dict(check=True, capture_output=True, text=True) if quiet else dict(check=True)
    obj = out + ".o"
    with open(asm_path, encoding="utf-8") as fh:
        dlls = windows_imports(fh.read())
    subprocess.run(["clang", "--target=x86_64-pc-windows-msvc", "-c", "-o", obj, asm_path], **run)
    libs = []
    for dll, names in dlls:
        stem = f"{out}.{dll.removesuffix('.dll')}"
        with open(stem + ".def", "w", encoding="utf-8") as fh:
            fh.write(f"LIBRARY {dll}\nEXPORTS\n" + "".join(n + "\n" for n in names))
        subprocess.run(["llvm-dlltool", "-m", "i386:x86-64", "-d", stem + ".def", "-l", stem + ".lib"], **run)
        libs.append(stem + ".lib")
    subprocess.run(["lld-link", "/nologo", "/Brepro", "/subsystem:console", "/entry:_start", "/nodefaultlib",
                    "/stack:125829120", "/out:" + out, obj, *libs], **run)


def _assemble(asm: str, out: str) -> None:
    """The assembly file `asm` assembled and linked into `out`."""
    if WINDOWS:
        link_windows(asm, out, quiet=False)
        return
    flags = ["--64"] if platform.machine() == "x86_64" else []   # x86-64's flag alone
    subprocess.run(["as", *flags, "-o", out + ".o", asm], check=True)
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
    stage0 = _cached("stage0", lambda out: _assemble(_SEED, out))
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


# A child's peak resident memory (`ru_maxrss`) counts the memory of the
# process it was forked from, as `exec` keeps the old image's peak; the test
# process grows to hundreds of MB over a run of the whole suite (MYLA-611).
# So a measured program is started from a minimal helper, which reports its
# exit code and peak (KB) on its last line of stderr. On Windows the peak is
# the process's own peak working set, read from its handle once it ended
# (K32GetProcessMemoryInfo, MYLA-926 step 2).
def measure_script(exe_first: bool, newline_first: bool) -> str:
    """The helper's Python source: its arguments the executable then the
    command line (`exe_first`) or the command line alone, its report line
    after a newline (`newline_first`) or not."""
    args = "exe, argv = sys.argv[1], sys.argv[2:]\n" if exe_first else "argv = sys.argv[1:]\nexe = argv[0]\n"
    nl = "\\n" if newline_first else ""
    if not WINDOWS:
        return ("import os, shutil, sys\n" + args +
                "path = exe if '/' in exe else shutil.which(exe)\n"
                "pid = os.posix_spawn(path, argv, os.environ)\n"
                "_, status, usage = os.wait4(pid, 0)\n"
                f"sys.stderr.write(f'{nl}{{os.waitstatus_to_exitcode(status)}} {{usage.ru_maxrss}}\\n')\n")
    return ("import ctypes, subprocess, sys\n"
            "from ctypes import wintypes\n" + args +
            "class Counters(ctypes.Structure):\n"
            "    _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + "
            "[(n, ctypes.c_size_t) for n in ('peak', 'ws', 'qpp', 'qp', 'qpnp', 'qnp', 'pf', 'peak_pf')]\n"
            "p = subprocess.Popen(argv, executable=exe)\n"
            "p.wait()\n"
            "c = Counters()\n"
            "c.cb = ctypes.sizeof(c)\n"
            "ctypes.windll.kernel32.K32GetProcessMemoryInfo(wintypes.HANDLE(int(p._handle)), ctypes.byref(c), c.cb)\n"
            f"sys.stderr.write(f'{nl}{{p.returncode}} {{c.peak // 1024}}\\n')\n")


_MEASURE = measure_script(exe_first=True, newline_first=True)


def peak_memory(argv: list[str], exe: str | None = None) -> tuple[str, int]:
    """(stdout, peak resident memory in KB) of running `argv` (the program
    `exe`, or `argv[0]`), which must succeed, started from a small helper so
    that the peak is the program's own (MYLA-611)."""
    import sys
    r = subprocess.run([sys.executable, "-I", "-c", _MEASURE, exe or argv[0], *argv],
                       capture_output=True, text=True)
    code, kb = r.stderr.rstrip("\n").rsplit("\n", 1)[-1].split()
    assert int(code) == 0, r.stderr
    return r.stdout, int(kb)
