"""Diagnostics and error types for the Myla toolchain.

Every error carries a source position (1-based line and column) and, when it is
about a token or a syntax node, the source range that covers it (MYLA-65). The
pipeline stages raise the matching subclass; the CLI renders them with the range
underlined on the position's line, e.g.::

    type error: cannot concatenate 'str' with 'int32'
      --> example.my:3:17
      |
    3 |     let x = "a" + 1
      |             ^^^^^^^

v0.0 uses panic-mode error handling: the first error in a stage aborts that
stage (see docs/Architecture.md).
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


# A source range: start line and column, then the line and column just past its
# end (all 1-based, columns in code points).
Span = tuple[int, int, int, int]


class MylaError(Exception):
    """Base class for all Myla compiler/interpreter errors.

    `kind` is a short human label used as the diagnostic prefix (e.g. "lex
    error"). `line`/`column` are 1-based; they may be None for errors without a
    precise location. `span` is the source range the error is about, or None
    (then the rendering marks just the column). `at` takes both from a token or
    a syntax node, which know their range. `path` is the file the position
    refers to, when known (set by `in_file` as the error leaves the module or
    declaration it came from; MYLA-10).
    """

    kind = "error"

    def __init__(self, message: str, line: int | None = None, column: int | None = None,
                 span: Span | None = None, *, at=None):
        super().__init__(message)
        if at is not None:
            line, column, span = at.line, at.column, at.span
        self.message = message
        self.line = line
        self.column = column
        self.span = span
        self.path: str | None = None

    def caret_range(self, text: str) -> tuple[int, int]:
        """The columns to underline on `text`, the error's line: (first, one
        past the last). The span's part on that line, to its end when the span
        goes on, and always the error's column."""
        col = self.column or 1
        first, end = col, col + 1
        if self.span is not None:
            sl, sc, el, ec = self.span
            if sl == self.line:
                first = sc
            end = ec if el == self.line else len(text) + 1
        return min(first, col), max(end, col + 1)

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
                    first, end = self.caret_range(src_lines[self.line - 1])
                    lines.append(f"{pad} | {' ' * (first - 1)}{'^' * (end - first)}")
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
