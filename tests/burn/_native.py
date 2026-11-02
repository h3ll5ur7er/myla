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
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

CAN_BUILD_NATIVE = (
    sys.platform.startswith("linux")
    and platform.machine() == "x86_64"
    and shutil.which("as") is not None
    and shutil.which("ld") is not None
)

SKIP_REASON = "native build requires x86-64 Linux with `as` and `ld`"


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

def native_build(program: Program, binary: str, entry_path: str | None = None, debug: bool = False) -> None:
    """Compile `program` to the native binary `binary` with the self-hosted CLI.
    `entry_path` names the entry file in runtime-error positions, as `myla
    build <entry_path>` would."""
    cmd = [selfhost_tool("main"), "build", entry_path or program.entry_file, "-o", binary,
           "--stdlib", STDLIB_ROOT]
    if debug:
        cmd.append("-g")
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
        proc = subprocess.run([binary], capture_output=True, text=True, timeout=timeout)
        return proc.stdout, proc.returncode


def build_and_run(source: str, timeout: float | None = None) -> tuple[str, int]:
    """Compile `source` to a native binary, run it, return (stdout, exit code)."""
    with tempfile.TemporaryDirectory() as tmp:
        return build_and_run_checker(Program(write_program(tmp, source)), timeout)


def build_and_run_full(program: Program, args=None, argv0="prog",
                       entry_path=None) -> tuple[str, str, int]:
    """Compile `program` to a native binary and run it, returning
    (stdout, stderr, exit). `args` are extra program arguments; `argv0` is the
    program name the binary sees as `argv[0]` (so the native argv can be made to
    match the interpreter's for parity); `entry_path` names the entry file in
    runtime-error positions, as `myla build <entry_path>` would."""
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "prog")
        native_build(program, binary, entry_path=entry_path)
        program_argv = [argv0, *(args or [])]
        proc = subprocess.run(program_argv, executable=binary,
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
