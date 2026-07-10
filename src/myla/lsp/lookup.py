"""Shared cursor/identifier helpers for the language-server features.

`identifier_at` finds the identifier under an LSP cursor, and `identifier_ranges`
finds every occurrence of a name in a buffer — both by re-lexing so they agree
with the compiler's own tokenization (comments, strings, and keywords are never
matched). Positions in/out are 0-based UTF-16 (LSP conventions).
"""
from __future__ import annotations

from ..errors import MylaError
from ..lexer import tokenize
from ..tokens import TokenKind
from .diagnostics import SourceRange
from .positions import to_lsp_position


def _tokens(source: str):
    try:
        return tokenize(source)
    except MylaError:
        return None
    except Exception:  # noqa: BLE001 - never raise into the server
        return None


def _token_range(lines: list[str], tok) -> SourceRange:
    start = to_lsp_position(lines, tok.line, tok.column)
    end = to_lsp_position(lines, tok.line, tok.column + len(tok.lexeme))
    return SourceRange(start[0], start[1], end[0], end[1])


def identifier_at(source: str, line: int, character: int) -> str | None:
    """Return the identifier lexeme covering the 0-based (`line`, `character`)
    position, or None if the cursor is not on an identifier."""
    tokens = _tokens(source)
    if tokens is None:
        return None
    lines = source.splitlines()
    for tok in tokens:
        if tok.kind is not TokenKind.IDENT or tok.line - 1 != line:
            continue
        rng = _token_range(lines, tok)
        if rng.start_col <= character <= rng.end_col:
            return tok.lexeme
    return None


def identifier_ranges(source: str, name: str) -> list[SourceRange]:
    """Return the ranges of every identifier token whose lexeme is `name`."""
    tokens = _tokens(source)
    if tokens is None:
        return []
    lines = source.splitlines()
    return [
        _token_range(lines, tok)
        for tok in tokens
        if tok.kind is TokenKind.IDENT and tok.lexeme == name
    ]
