"""Go to Definition for Myla source.

Intra-file first: the identifier under the cursor (found by `lookup`) is matched
by name against the document's own declarations (`symbols.best_match`). If it
isn't declared in the current file, an optional workspace resolver provides a
cross-file fallback so a call/type reference can jump to a declaration in
another `.my` file.

It is deliberately name-based rather than type-aware: no scope or receiver-type
resolution, so an ambiguous name resolves to the highest-priority declaration.
A later pass can use the checker's symbol table for precise resolution.
"""
from __future__ import annotations

from typing import Callable

from .diagnostics import Location
from .lookup import identifier_at
from .symbols import best_match, document_symbols

# A resolver mapping a name to cross-file declaration locations (workspace index).
WorkspaceResolver = Callable[[str], list[Location]]


def definition_at(
    path: str,
    source: str,
    line: int,
    character: int,
    resolver: WorkspaceResolver | None = None,
) -> Location | None:
    """Return the declaration `Location` for the identifier at the 0-based
    (`line`, `character`) position, or None."""
    ident = identifier_at(source, line, character)
    if ident is None:
        return None

    local = best_match(document_symbols(path, source), ident)
    if local is not None:
        return Location(path=path, range=local.selection_range)

    if resolver is not None:
        matches = resolver(ident)
        if matches:
            return matches[0]

    return None

