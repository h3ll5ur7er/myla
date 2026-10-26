"""Native (x86-64) compiler backend for Myla v0.0.

`compile_to_asm` turns a type-checked program into GAS assembly text;
`build` writes that assembly out and drives the system `as`/`ld` to produce a
native ELF binary (no libc — see docs/Architecture/Native-backend.md).
"""
from __future__ import annotations

import os
import subprocess

from ..types import Checker
from .codegen_x86 import generate as _generate
from .monomorphize import monomorphize


class BuildError(Exception):
    """A failure while assembling or linking the generated program."""


def compile_to_asm(checker: Checker, debug: bool = False) -> str:
    """Return GAS/AT&T x86-64 assembly for a type-checked program.

    Generics are monomorphized away first (D13), so codegen only ever sees
    concrete types. With `debug`, the assembly carries `.file`/`.loc` line
    directives, from which the assembler builds a DWARF line table (MYLA-71).
    """
    return _generate(monomorphize(checker), debug=debug)


def build(checker: Checker, output: str, keep_asm: bool = False,
          debug: bool = False) -> str:
    """Compile, assemble, and link `checker`'s program into `output`.

    Returns the path to the produced binary. Intermediate `.s`/`.o` files are
    written next to `output`; the object file is always removed and the assembly
    is removed unless `keep_asm` is set.
    """
    asm = compile_to_asm(checker, debug=debug)
    asm_path = output + ".s"
    obj_path = output + ".o"

    with open(asm_path, "w", encoding="utf-8") as fh:
        fh.write(asm)

    try:
        _run(["as", "--64", "-o", obj_path, asm_path], "assembler (as)")
        _run(["ld", "-o", output, obj_path], "linker (ld)")
    finally:
        _silent_remove(obj_path)
        if not keep_asm:
            _silent_remove(asm_path)

    return output


def _run(cmd: list[str], stage: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise BuildError(
            f"{stage} failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )


def _silent_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
