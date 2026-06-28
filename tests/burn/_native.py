"""Shared helpers for native-compilation burn tests.

These helpers build a Myla program to a real ELF binary with the system
`as`/`ld` and run it, plus run the same source through the interpreter, so tests
can assert the two agree. They are skipped automatically when the host can't
produce/run the binary (non-x86-64, non-Linux, or no assembler/linker).
"""
from __future__ import annotations

import io
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from myla.compiler import build
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.loader import default_stdlib_root, link
from myla.parser import parse
from myla.types import check

CAN_BUILD_NATIVE = (
    sys.platform.startswith("linux")
    and platform.machine() == "x86_64"
    and shutil.which("as") is not None
    and shutil.which("ld") is not None
)

SKIP_REASON = "native build requires x86-64 Linux with `as` and `ld`"


def interpret_checker(checker) -> str:
    out = io.StringIO()
    Interpreter(checker, out).run()
    return out.getvalue()


def build_and_run_checker(checker) -> tuple[str, int]:
    """Compile an already-checked program to a native binary, run it, and return
    (stdout, exit code)."""
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "prog")
        build(checker, binary)
        proc = subprocess.run([binary], capture_output=True, text=True)
        return proc.stdout, proc.returncode


def interpret(source: str) -> str:
    return interpret_checker(check(parse(tokenize(source))))


def build_and_run(source: str) -> tuple[str, int]:
    """Compile `source` to a native binary, run it, return (stdout, exit code)."""
    return build_and_run_checker(check(parse(tokenize(source))))


# -- stdlib-aware helpers (v0.5.4) -----------------------------------------
# These link the import graph (so `from std.… import …` resolves to the bundled
# standard library) and observe stdout, stderr, and the process exit status, so
# burn tests can assert interpreter/native parity for the freestanding I/O
# runtime.


def check_file(path: str):
    """Link the module graph rooted at `path` (with the bundled stdlib on the
    search path) and type-check the merged program."""
    return check(link(path, stdlib_root=default_stdlib_root()))


def write_program(directory: str, source: str, name: str = "main.my") -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(source)
    return path


def interpret_full(checker, argv=None) -> tuple[str, str, int]:
    """Run `checker` through the interpreter, returning (stdout, stderr, exit).
    `argv` is the program's command line (what `std.process.args` returns)."""
    out, err = io.StringIO(), io.StringIO()
    code = Interpreter(checker, out, err, argv=argv).run()
    return out.getvalue(), err.getvalue(), code


def build_and_run_full(checker, args=None, argv0="prog") -> tuple[str, str, int]:
    """Compile `checker` to a native binary and run it, returning
    (stdout, stderr, exit). `args` are extra program arguments; `argv0` is the
    program name the binary sees as `argv[0]` (so the native argv can be made to
    match the interpreter's for parity)."""
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "prog")
        build(checker, binary)
        program_argv = [argv0, *(args or [])]
        proc = subprocess.run(program_argv, executable=binary,
                              capture_output=True, text=True)
        return proc.stdout, proc.stderr, proc.returncode


def run_source_both(source: str, args=None) -> tuple[str, str, int]:
    """Link/check `source` (a single entry module that may import `std.…`), then
    assert the interpreter and native backend agree on (stdout, stderr, exit).
    `args` are extra program arguments; both backends observe the same argv
    (`["prog", *args]`). Returns that common (stdout, stderr, exit) triple."""
    argv0 = "prog"
    program_argv = [argv0, *(args or [])]
    with tempfile.TemporaryDirectory() as tmp:
        path = write_program(tmp, source)
        interp = interpret_full(check_file(path), argv=program_argv)
        native = build_and_run_full(check_file(path), args=args, argv0=argv0)
    assert interp == native, f"interpreter {interp!r} != native {native!r}"
    return interp
