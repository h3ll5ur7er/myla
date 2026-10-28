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

A stage may find more than one error (MYLA-65, D80): the parser resumes at the
next statement or declaration, the checker checks every function on its own.
It raises the first one, the error a single-error run would report, with the
others in its `more` list, in the order they were found.

An error may carry notes (MYLA-65): a `note` about another place in the same
file, shown with its line like the error, or a `help` line without one::

    type error: cannot assign to an immutable binding (declare it with 'var')
      --> example.my:3:5
      |
    3 |     n = 2
      |     ^^^^^
    note: 'n' is declared here
      --> example.my:2:5
      |
    2 |     let n = 1
      |     ^^^^^^^^^
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


# At most this many errors per run (MYLA-65, D80): the parser and the checker
# stop at the limit.
MAX_ERRORS = 20


# A source range: start line and column, then the line and column just past its
# end (all 1-based, columns in code points).
Span = tuple[int, int, int, int]


@dataclass
class Note:
    """A note on an error (MYLA-65): `label` is "note", about the place `line`,
    `column` and `span` give in the error's file, or "help", without a place."""

    label: str
    message: str
    line: int | None = None
    column: int | None = None
    span: Span | None = None


def note(message: str, at) -> Note:
    """A note about `at`, a token or a syntax node."""
    return Note("note", message, at.line, at.column, at.span)


def hint(message: str) -> Note:
    """A help line."""
    return Note("help", message)


def caret_range(text: str, line: int, column: int | None, span: Span | None) -> tuple[int, int]:
    """The columns to underline on `text`, line `line` of a diagnostic at
    `column` with range `span`: (first, one past the last). The span's part on
    that line, to its end when the span goes on, and always the column."""
    col = column or 1
    first, end = col, col + 1
    if span is not None:
        sl, sc, el, ec = span
        if sl == line:
            first = sc
        end = ec if el == line else len(text) + 1
    return min(first, col), max(end, col + 1)


def _located(header: str, line: int | None, column: int | None, span: Span | None,
             source: str | None, filename: str) -> list[str]:
    """`header`, then the place and the source line with its carets."""
    if line is None:
        return [header]
    location = f"  --> {filename}:{line}"
    if column is not None:
        location += f":{column}"
    lines = [header, location]
    if source is not None:
        src_lines = source.splitlines()
        if 1 <= line <= len(src_lines):
            gutter = str(line)
            pad = " " * len(gutter)
            lines.append(f"{pad} |")
            lines.append(f"{gutter} | {src_lines[line - 1]}")
            if column is not None:
                first, end = caret_range(src_lines[line - 1], line, column, span)
                lines.append(f"{pad} | {' ' * (first - 1)}{'^' * (end - first)}")
    return lines


class MylaError(Exception):
    """Base class for all Myla compiler/interpreter errors.

    `kind` is a short human label used as the diagnostic prefix (e.g. "lex
    error"). `line`/`column` are 1-based; they may be None for errors without a
    precise location. `span` is the source range the error is about, or None
    (then the rendering marks just the column). `at` takes both from a token or
    a syntax node, which know their range. `path` is the file the position
    refers to, when known (set by `in_file` as the error leaves the module or
    declaration it came from; MYLA-10). `more` holds the errors the same stage
    found after this one (D80); only the first error of a run has any. `notes`
    are its notes and help lines (MYLA-65).
    """

    kind = "error"

    def __init__(self, message: str, line: int | None = None, column: int | None = None,
                 span: Span | None = None, *, at=None, notes: list[Note] | None = None):
        super().__init__(message)
        if at is not None:
            line, column, span = at.line, at.column, at.span
        self.message = message
        self.line = line
        self.column = column
        self.span = span
        self.path: str | None = None
        self.more: list[MylaError] = []
        self.notes: list[Note] = list(notes or [])

    def caret_range(self, text: str) -> tuple[int, int]:
        """The columns to underline on `text`, the error's line (see
        `caret_range`)."""
        return caret_range(text, self.line, self.column, self.span)

    def render(self, source: str | None = None, filename: str = "<input>") -> str:
        """Format the error and its notes as a multi-line diagnostic string."""
        lines = _located(f"{self.kind}: {self.message}", self.line, self.column,
                         self.span, source, filename)
        for n in self.notes:
            lines += _located(f"{n.label}: {n.message}", n.line, n.column, n.span,
                              source, filename)
        return "\n".join(lines)


@contextlib.contextmanager
def in_file(path: str | None):
    """Attribute a MylaError raised inside the block (and the errors in its
    `more`) to `path`, unless an inner block already did."""
    try:
        yield
    except MylaError as err:
        for e in (err, *err.more):
            if e.path is None:
                e.path = path
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
