"""Shared helpers for native-compilation burn tests.

These helpers build a Myla program to a real ELF binary with the self-hosted
compiler (`myla build` of the natively built CLI, MYLA-235) and run it, and
give what the interpreter printed for the same program, so tests can assert
the two agree. They are skipped automatically when the host can't produce or
run the binary (non-x86-64, non-Linux, or no assembler/linker).

The interpreter's answers are the retired Python interpreter's, recorded
(`tests/burn/_golden.py`, MYLA-219); `selfhost_run` runs the self-hosted one.
"""
from __future__ import annotations

import io
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from tests.burn._golden import golden
from tests.burn._tools import EXE, STDLIB_ROOT, link_windows, selfhost_tool, windows_imports  # noqa: F401

# The machine's own target, as `myla build` names it without `--target`
# (x86-64 or aarch64 Linux, MYLA-163; x86-64 Windows, MYLA-926 step 2; ""
# for another machine), and whether its programs can be built and run here:
# on Linux with `as` and `ld`, on Windows with LLVM's clang, llvm-dlltool and
# lld-link (D211).
if sys.platform == "win32":
    HOST_TARGET = "x86_64-windows" if platform.machine().upper() in ("AMD64", "X86_64") else ""
    _HOST_TOOLS = ["clang", "llvm-dlltool", "lld-link"]
elif sys.platform.startswith("linux"):
    HOST_TARGET = {"x86_64": "x86_64-linux", "aarch64": "aarch64-linux"}.get(platform.machine(), "")
    _HOST_TOOLS = ["as", "ld"]
else:
    HOST_TARGET, _HOST_TOOLS = "", []

CAN_BUILD_NATIVE = HOST_TARGET != "" and all(shutil.which(t) is not None for t in _HOST_TOOLS)

SKIP_REASON = ("native build requires x86-64 or aarch64 Linux with `as` and `ld`, "
               "or x86-64 Windows with clang, llvm-dlltool and lld-link")

# The target native builds are for (MYLA-268): the machine's, or the one
# MYLA_TEST_TARGET names (aarch64-linux, run under qemu-aarch64; wasm32-wasi,
# run under Node with tools/wasm/run.mjs; x86_64-windows, run under Wine,
# MYLA-702). scripts/test-target.py runs the
# suites tests/burn/_targets.py lists for a target with it set.
TEST_TARGET = os.environ.get("MYLA_TEST_TARGET", "")

# What the programs the tests build are for: MYLA_TEST_TARGET's target, else
# the machine's. A test that reads x86-64 Linux code (its assembly, its
# registers under gdb) keys on it, not only on MYLA_TEST_TARGET, so that it
# is skipped on an aarch64 machine as on the aarch64 target (MYLA-926).
BUILD_TARGET = TEST_TARGET or HOST_TARGET
READS_X86 = CAN_BUILD_NATIVE and BUILD_TARGET == "x86_64-linux"
X86_REASON = "it reads x86-64 Linux code (built for x86-64 Linux only)"

# A test that can't run on Windows itself (a pty, a Unix signal, /proc, a
# FIFO, a Linux tool), marked so with its reason, never skipped silently
# (MYLA-926 step 2): `@linux_only("Unix ptys and termios")`.
ON_WINDOWS = sys.platform == "win32"


def shown(path: str) -> str:
    """`path` as myla's messages write a source file's path: with `/` for each
    `\\` on Windows, as the loader keeps paths there (MYLA-931; `--> C:/w/main.my:2:5`);
    as it is elsewhere (MYLA-926)."""
    return path.replace("\\", "/") if ON_WINDOWS else path


def linux_only(reason: str):
    """The decorator that skips a test or class on Windows, saying why."""
    import unittest
    return unittest.skipIf(ON_WINDOWS, f"Linux-only: {reason}")


# The machine's assembler as the tests call it: `--64` is only x86-64's flag.
AS_CMD = ["as", "--64"] if HOST_TARGET == "x86_64-linux" else ["as"]
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_RUN_MJS = os.path.join(_ROOT, "tools", "wasm", "run.mjs")


# Windows' programs run under Wine (D213, MYLA-702): the command for it is
# MYLA_EMULATOR's words when the suites run for x86_64-windows
# (`scripts/test-target.py` sets it), else `wine` or `wine64` on PATH, else
# where Ubuntu's `wine64` package puts it (that package alone puts nothing
# on PATH).
_WINE_PATHS = ["/usr/lib/wine/wine64"]
_WINE_RUN = os.path.join(_ROOT, "tests", "burn", "_wine_run.py")


def wine() -> list[str]:
    """The command a Windows program runs under here; [] for none. (Wine's
    own: MYLA_EMULATOR's words after `_wine_run.py` when they start with
    it, as `wine_run` gives them.)"""
    words = os.environ.get("MYLA_EMULATOR", "").split() if TEST_TARGET == "x86_64-windows" else []
    if _WINE_RUN in words:
        words = words[words.index(_WINE_RUN) + 1:]
    if words:
        return words
    for name in ("wine", "wine64"):
        found = shutil.which(name)
        if found:
            return [found]
    return [p for p in _WINE_PATHS if os.access(p, os.X_OK)][:1]


def wine_run() -> list[str]:
    """`wine()` behind `_wine_run.py`, which becomes the program (its pid,
    signals and time limits are the program's) with its output copied, so
    that the output ends when the program does (MYLA-759: Wine's services,
    started by the first program of a server, held its standard error, and
    a test reading it waited for them); [] for no Wine. The command for a
    test's runs of a Windows program, and MYLA_EMULATOR's for `myla test
    --target x86_64-windows`."""
    words = wine()
    return [sys.executable, "-I", "-S", _WINE_RUN, *words] if words else []


def wine_server() -> str:
    """Wine's server next to its command (`wineserver`; Ubuntu's package
    puts it beside `wine64`, not on PATH); "" for none."""
    words = wine()
    found = shutil.which("wineserver") or (os.path.join(os.path.dirname(words[0]), "wineserver") if words else "")
    return found if found and os.access(found, os.X_OK) else ""


def wine_env(persist: str = "60") -> None:
    """Wine's defaults in this process's environment, for it and its children
    (`myla test --target x86_64-windows`'s runs among them): no debug output,
    a UTF-8 locale, and a prefix of the repository's own under build/, made
    here if it isn't there yet (some seconds).

    Its services are started here too, their standard streams /dev/null. Wine
    starts them from the first program of a new server, which they outlive
    holding its standard streams: a test reading a program's output would wait
    for them, while the server lives, never seeing the end. The server is
    started once the prefix is there (a new prefix is made and its setup
    waited for first, MYLA-759), kept `persist` seconds after its last
    program (`-p60`;
    scripts/test-target.py starts its own for the whole run, `-p`, which this
    finds running), so the services aren't started again between tests."""
    os.environ.setdefault("WINEDEBUG", "-all")
    os.environ.setdefault("WINEPREFIX", os.path.join(_ROOT, "build", "wineprefix"))
    # a UTF-8 locale, which Wine converts a program's arguments, environment
    # and paths from: in the C locale an argument `é中` came as `C)d8-` (MYLA-798)
    if "UTF-8" not in os.environ.get("LC_ALL", os.environ.get("LANG", "")).upper().replace("UTF8", "UTF-8"):
        os.environ["LC_ALL"] = "C.UTF-8"
    if not wine():
        return
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    server = wine_server()
    if not os.path.isdir(os.environ["WINEPREFIX"]):
        # the prefix made first, and its setup waited for to its end (its
        # server stopped): a server can't start on a prefix that isn't there
        # yet, and one started before would have stopped at once, leaving
        # the suites to a server of the boot's, setting up as they ran
        # (MYLA-759: CI's runners start with no prefix)
        subprocess.run([*wine(), "wineboot", "--init"], timeout=300, **quiet)
        if server:
            subprocess.run([server, "-w"], timeout=300, **quiet)
    if server:
        subprocess.run([server, "-p" + persist], **quiet)
    subprocess.run([*wine(), "wineboot"], timeout=300, **quiet)


def target_flags() -> list[str]:
    """The `--target` a build for TEST_TARGET takes (none for the machine)."""
    return ["--target", TEST_TARGET] if TEST_TARGET else []


def run_argv(binary: str, argv0: str = "prog", args=()) -> tuple[list[str], str | None]:
    """The command that runs `binary` with `argv0` as its `argv[0]` and
    `args`, and the executable for subprocess (None: the command's first)."""
    if TEST_TARGET == "aarch64-linux":
        return ["qemu-aarch64", "-0", argv0, binary, *args], None
    if TEST_TARGET == "wasm32-wasi":
        return ["node", _RUN_MJS, "--argv0", argv0, binary, *args], None
    if TEST_TARGET == "x86_64-windows":
        # (Wine gives a program its Windows path as `argv[0]`, not `argv0`)
        return [*wine_run(), binary, *args], None
    return [argv0, *args], binary


def assemble(asm_path: str, out: str) -> None:
    """Assemble and link the compiler's assembly `asm_path` for TEST_TARGET."""
    obj = out + ".o"
    if TEST_TARGET == "aarch64-linux":
        subprocess.run(["clang", "--target=aarch64-linux-gnu", "-c", "-o", obj, asm_path], check=True,
                       capture_output=True, text=True)
        subprocess.run(["ld.lld", "-static", "-o", out, obj], check=True, capture_output=True, text=True)
    elif TEST_TARGET == "wasm32-wasi":
        subprocess.run(["clang", "--target=wasm32-wasi", "-mtail-call", "-mbulk-memory", "-mnontrapping-fptoint",
                        "-msign-ext", "-c", "-o", obj, asm_path], check=True, capture_output=True, text=True)
        subprocess.run(["wasm-ld", "--stack-first", "-z", "stack-size=8388608", "-o", out, obj], check=True,
                       capture_output=True, text=True)
    elif BUILD_TARGET == "x86_64-windows":
        # as `myla build` does (D211): an import library of each DLL the
        # program calls, made from the functions it calls of it (MYLA-722);
        # under Wine on Linux, or on Windows itself (MYLA-926)
        link_windows(asm_path, out)
    else:
        subprocess.run([*AS_CMD, "-o", obj, asm_path], check=True, capture_output=True, text=True)
        subprocess.run(["ld", "-o", out, obj], check=True, capture_output=True, text=True)


class Program:
    """A program named by its entry file (what `check_file` gives)."""

    def __init__(self, path: str):
        self.entry_file = path


def check_file(path: str) -> Program:
    """The program whose entry file is `path` (it was type-checked here when
    the Python toolchain existed; the self-hosted CLI checks it now)."""
    return Program(path)


def write_program(directory: str, source: str, name: str = "main.my") -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(source)
    return path


# -- the interpreter's answers (recorded) ------------------------------------

@golden("interpret")
def interpret(source: str) -> str:
    """What the interpreter prints for `source` (a single module)."""
    from myla.interpreter import Interpreter
    from myla.lexer import tokenize
    from myla.parser import parse
    from myla.types import check
    out = io.StringIO()
    Interpreter(check(parse(tokenize(source))), out).run()
    return out.getvalue()


@golden("interpret_full")
def _interpret_file(path: str, argv) -> tuple[str, str, int]:
    from myla.interpreter import Interpreter
    from myla.loader import default_stdlib_root, link
    from myla.types import check
    out, err = io.StringIO(), io.StringIO()
    code = Interpreter(check(link(path, stdlib_root=default_stdlib_root())), out, err, argv=argv).run()
    return out.getvalue(), err.getvalue(), code


def interpret_full(program: Program, argv=None) -> tuple[str, str, int]:
    """(stdout, stderr, exit) of the interpreter running `program`; `argv` is
    the program's command line (what `std.process.args` returns)."""
    return _interpret_file(program.entry_file, list(argv) if argv is not None else None)


def interpret_checker(program: Program) -> str:
    return interpret_full(program)[0]


def selfhost_run(path: str, args=None, cwd: str | None = None) -> tuple[str, str, int]:
    """(stdout, stderr, exit) of `myla run path args…` in the self-hosted
    interpreter."""
    proc = subprocess.run([selfhost_tool("main"), "run", path, *(args or []), "--stdlib", STDLIB_ROOT],
                          capture_output=True, text=True, cwd=cwd)
    return proc.stdout, proc.stderr, proc.returncode


# -- native builds -------------------------------------------------------------

def native_build(program: Program, binary: str, entry_path: str | None = None, debug: bool = False,
                 checked: bool = False) -> None:
    """Compile `program` to the native binary `binary` with the self-hosted CLI.
    `entry_path` names the entry file in runtime-error positions, as `myla
    build <entry_path>` would; `checked`: integer overflow traps (`--checked`,
    D175)."""
    cmd = [selfhost_tool("main"), "build", entry_path or program.entry_file, "-o", binary,
           "--stdlib", STDLIB_ROOT, *target_flags()]
    if debug:
        cmd.append("-g")
    if checked:
        cmd.append("--checked")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"myla build {program.entry_file} failed:\n{proc.stderr}")


def build_and_run_checker(program: Program, timeout: float | None = None) -> tuple[str, int]:
    """Compile `program` to a native binary, run it, and return (stdout, exit
    code). With `timeout` (seconds), a run that takes longer raises
    `subprocess.TimeoutExpired`."""
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "prog")
        native_build(program, binary)
        argv, exe = run_argv(binary)
        proc = subprocess.run(argv, executable=exe, capture_output=True, text=True, timeout=timeout)
        return proc.stdout, proc.returncode


def build_and_run(source: str, timeout: float | None = None) -> tuple[str, int]:
    """Compile `source` to a native binary, run it, return (stdout, exit code)."""
    with tempfile.TemporaryDirectory() as tmp:
        return build_and_run_checker(Program(write_program(tmp, source)), timeout)


def build_and_run_full(program: Program, args=None, argv0="prog",
                       entry_path=None, checked: bool = False) -> tuple[str, str, int]:
    """Compile `program` to a native binary and run it, returning
    (stdout, stderr, exit). `args` are extra program arguments; `argv0` is the
    program name the binary sees as `argv[0]` (so the native argv can be made to
    match the interpreter's for parity); `entry_path` names the entry file in
    runtime-error positions, as `myla build <entry_path>` would; `checked`:
    built with `--checked`."""
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "prog")
        native_build(program, binary, entry_path=entry_path, checked=checked)
        program_argv, exe = run_argv(binary, argv0, args or [])
        proc = subprocess.run(program_argv, executable=exe,
                              capture_output=True, text=True)
        return proc.stdout, proc.stderr, proc.returncode


def run_source_both(source: str, args=None) -> tuple[str, str, int]:
    """`source` (a single entry module that may import `std.…`) run by the
    interpreter and as a native binary: both must agree on (stdout, stderr,
    exit), which is returned. Both see the same argv (`["prog", *args]`)."""
    argv0 = "prog"
    program_argv = [argv0, *(args or [])]
    with tempfile.TemporaryDirectory() as tmp:
        path = write_program(tmp, source)
        interp = interpret_full(check_file(path), argv=program_argv)
        native = build_and_run_full(check_file(path), args=args, argv0=argv0)
    assert interp == native, f"interpreter {interp!r} != native {native!r}"
    return interp


def run_file_both_now(path: str, args=None) -> tuple[str, str, int]:
    """`path` run by today's self-hosted interpreter (`myla run`) and as a
    native binary, which must agree on (stdout, stderr, exit), returned. For
    programs no recorded answer of the retired Python toolchain covers (new,
    or changed in what they print, as D129 changed I/O errors): each test gives
    its own expectation. Both see the file's path as `argv[0]`."""
    interp = selfhost_run(path, args)
    native = build_and_run_full(Program(path), args=args, argv0=path)
    assert interp == native, f"interpreter {interp!r} != native {native!r}"
    return interp


def run_source_both_now(source: str, args=None) -> tuple[str, str, int]:
    """`run_file_both_now` for a program's text."""
    with tempfile.TemporaryDirectory() as tmp:
        return run_file_both_now(write_program(tmp, source), args)
