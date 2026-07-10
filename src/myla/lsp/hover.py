"""Hover for Myla source.

Shows the declaration of the identifier under the cursor as a Markdown snippet:
a function signature, a type/const/field/variant with its type, etc. Resolution
is the same name-based lookup used by go-to-definition — local declarations
first, then an optional workspace resolver for cross-file symbols.
"""
from __future__ import annotations

from typing import Callable

from .lookup import identifier_at
from .symbols import Symbol, SymbolKind, best_match, document_symbols

HoverResolver = Callable[[str], "Symbol | None"]

_KEYWORD = {
    SymbolKind.STRUCT: "struct",
    SymbolKind.ENUM: "enum",
    SymbolKind.INTERFACE: "trait",
    SymbolKind.IMPL: "impl",
}


def hover_at(
    path: str,
    source: str,
    line: int,
    character: int,
    resolver: HoverResolver | None = None,
) -> str | None:
    """Return Markdown hover content for the identifier at the 0-based
    (`line`, `character`) position, or None."""
    ident = identifier_at(source, line, character)
    if ident is None:
        return None

    sym = best_match(document_symbols(path, source), ident)
    if sym is None and resolver is not None:
        sym = resolver(ident)
    if sym is None:
        return None

    return "```myla\n" + _render(sym) + "\n```"


def _render(sym: Symbol) -> str:
    if sym.kind in (SymbolKind.FUNCTION, SymbolKind.METHOD):
        # detail already holds the full `fun name(...) -> T` signature.
        return sym.detail or f"fun {sym.name}"
    if sym.kind in _KEYWORD:
        return f"{_KEYWORD[sym.kind]} {sym.name}"
    if sym.kind is SymbolKind.ENUM_MEMBER:
        return f"{sym.name}{sym.detail}"  # detail is the payload, e.g. "(int)"
    if sym.kind is SymbolKind.FIELD:
        return f"{sym.name}: {sym.detail}"
    if sym.kind is SymbolKind.CONSTANT:
        return f"const {sym.name}: {sym.detail}"
    if sym.kind is SymbolKind.TYPE_ALIAS:
        return f"typealias {sym.name} = {sym.detail}"
    return sym.name
