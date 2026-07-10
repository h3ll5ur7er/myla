"""Position conversion between the Myla compiler and LSP.

The compiler reports **1-based** line/column numbers (see errors.Position), and
a column counts Unicode scalar values (Python ``str`` indexing). LSP positions
are **0-based** and a character offset counts **UTF-16 code units** within the
line (LSP spec, default position encoding).

All conversion lives here so the rest of the server never juggles the two
conventions. Ranges are clamped to the document so a stray out-of-bounds
position can never produce an invalid LSP range.
"""
from __future__ import annotations


def _utf16_len(text: str) -> int:
    """Number of UTF-16 code units needed to encode `text`.

    Characters outside the Basic Multilingual Plane (code point > 0xFFFF) take
    two UTF-16 code units (a surrogate pair); everything else takes one."""
    return len(text) + sum(1 for ch in text if ord(ch) > 0xFFFF)


def to_lsp_position(
    source_lines: list[str], line_1based: int, col_1based: int
) -> tuple[int, int]:
    """Convert a 1-based compiler (line, column) into a 0-based LSP
    (line, character) using UTF-16 offsets, clamped to the document.

    `source_lines` is the document split with ``str.splitlines()``. A missing or
    non-positive line/column defaults to the start of the document."""
    if not source_lines:
        return (0, 0)

    line = max(line_1based, 1) - 1
    line = min(line, len(source_lines) - 1)

    text = source_lines[line]
    col = max(col_1based, 1) - 1
    col = min(col, len(text))  # allow one-past-end (caret after last char)
    return (line, _utf16_len(text[:col]))


def identifier_end_column(text: str, col_1based: int) -> int:
    """Best-effort end column (1-based, exclusive) for a diagnostic that only
    carries a start position.

    The compiler reports a single point; to draw a squiggle of non-zero width we
    extend across the identifier/number token that begins at the start column.
    If the character there is not identifier-like we advance a single column."""
    start = max(col_1based, 1) - 1
    if start >= len(text):
        return col_1based + 1

    ch = text[start]
    if ch.isalnum() or ch == "_":
        end = start
        while end < len(text) and (text[end].isalnum() or text[end] == "_"):
            end += 1
        return end + 1
    return col_1based + 1
