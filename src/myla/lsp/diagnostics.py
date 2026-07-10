"""Compiler-independent diagnostic model.

The adapter produces these plain dataclasses; `server.py` converts them into
`lsprotocol` types. Keeping an intermediate model means the compiler adapter has
no dependency on pygls/lsprotocol and is trivially unit-testable.

Positions here are already **0-based** and **UTF-16**-based (LSP conventions);
the conversion happens in the adapter via `positions.to_lsp_position`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DiagnosticSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


@dataclass(frozen=True)
class SourceRange:
    """A 0-based, UTF-16 half-open range within a single document."""

    start_line: int
    start_col: int
    end_line: int
    end_col: int


@dataclass(frozen=True)
class Location:
    """A `SourceRange` together with the file path it belongs to."""

    path: str
    range: SourceRange


@dataclass(frozen=True)
class CompilerDiagnostic:
    range: SourceRange
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    code: str | None = None
    source: str = "myla"
