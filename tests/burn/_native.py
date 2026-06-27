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
from myla.parser import parse
from myla.types import check

CAN_BUILD_NATIVE = (
    sys.platform.startswith("linux")
    and platform.machine() == "x86_64"
    and shutil.which("as") is not None
    and shutil.which("ld") is not None
)

SKIP_REASON = "native build requires x86-64 Linux with `as` and `ld`"


def interpret(source: str) -> str:
    checker = check(parse(tokenize(source)))
    out = io.StringIO()
    Interpreter(checker, out).run()
    return out.getvalue()


def build_and_run(source: str) -> tuple[str, int]:
    """Compile `source` to a native binary, run it, return (stdout, exit code)."""
    checker = check(parse(tokenize(source)))
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "prog")
        build(checker, binary)
        proc = subprocess.run([binary], capture_output=True, text=True)
        return proc.stdout, proc.returncode
