"""Diagnostics and error types for the Myla toolchain.

Every error carries a source position (1-based line and column). The pipeline
stages raise the matching subclass; the CLI renders them with a caret pointing
at the offending column, e.g.::

    error: unexpected character '$'
      --> example.my:3:5
       |
     3 |     $foo
       |     ^

v0.0 uses panic-mode error handling: the first error in a stage aborts that
stage (see docs/architecture.md §8).
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """A 1-based location in a source file."""

    line: int
    column: int

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.line}:{self.column}"


class MylaError(Exception):
    """Base class for all Myla compiler/interpreter errors.

    `kind` is a short human label used as the diagnostic prefix (e.g. "lex
    error"). `line`/`column` are 1-based; they may be None for errors without a
    precise location. `path` is the file the position refers to, when known
    (set by `in_file` as the error leaves the module or declaration it came
    from; MYLA-10).
    """

    kind = "error"

    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.path: str | None = None

    def render(self, source: str | None = None, filename: str = "<input>") -> str:
        """Format the error as a multi-line diagnostic string."""
        header = f"{self.kind}: {self.message}"
        if self.line is None:
            return header

        location = f"  --> {filename}:{self.line}"
        if self.column is not None:
            location += f":{self.column}"

        lines = [header, location]
        if source is not None:
            src_lines = source.splitlines()
            if 1 <= self.line <= len(src_lines):
                gutter = str(self.line)
                pad = " " * len(gutter)
                lines.append(f"{pad} |")
                lines.append(f"{gutter} | {src_lines[self.line - 1]}")
                if self.column is not None:
                    caret_pad = " " * (self.column - 1)
                    lines.append(f"{pad} | {caret_pad}^")
        return "\n".join(lines)


@contextlib.contextmanager
def in_file(path: str | None):
    """Attribute a MylaError raised inside the block to `path`, unless an inner
    block already did."""
    try:
        yield
    except MylaError as err:
        if err.path is None:
            err.path = path
        raise


class LexError(MylaError):
    kind = "lex error"


class ParseError(MylaError):
    kind = "parse error"


class TypeCheckError(MylaError):
    """Named TypeCheckError to avoid shadowing the builtin ``TypeError``."""

    kind = "type error"


class ModuleError(MylaError):
    """Import/module resolution failures (v0.5): unresolved paths, ambiguous
    file/package names, visibility violations, import collisions, etc."""

    kind = "module error"


class MylaRuntimeError(MylaError):
    kind = "runtime error"
