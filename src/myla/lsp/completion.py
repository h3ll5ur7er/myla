"""Completion for Myla source.

A pragmatic, mostly name-based provider:
  * after a `.` — member names (fields, methods, enum variants) from the file
    and workspace (no receiver-type inference yet, so it's a superset);
  * otherwise — keywords plus top-level declarations from the file and the
    workspace.

Completion is intentionally conservative: the editor filters by the typed
prefix, so offering a superset is acceptable and never blocks the user.
"""
from __future__ import annotations

from dataclasses import dataclass

from .positions import from_lsp_character
from .symbols import Symbol, SymbolKind, document_symbols, flatten

# Reserved words / built-in type names offered as keyword completions.
KEYWORDS = [
    "fun", "struct", "enum", "trait", "impl", "typealias", "const",
    "import", "from", "as", "pub", "let", "var", "return", "if", "else",
    "match", "while", "for", "in", "break", "continue", "self", "true", "false",
    "bool", "str", "char", "int", "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64", "float", "float32", "float64",
]

_MEMBER_KINDS = {SymbolKind.FIELD, SymbolKind.METHOD, SymbolKind.ENUM_MEMBER}
_TOPLEVEL_KINDS = {
    SymbolKind.FUNCTION, SymbolKind.STRUCT, SymbolKind.ENUM,
    SymbolKind.INTERFACE, SymbolKind.CONSTANT, SymbolKind.TYPE_ALIAS,
}


@dataclass(frozen=True)
class Completion:
    label: str
    kind: str  # "keyword" or a SymbolKind value
    detail: str


def completions(
    path: str,
    source: str,
    line: int,
    character: int,
    workspace_symbols: list[Symbol] | None = None,
) -> list[Completion]:
    lines = source.splitlines()
    member_mode = _is_member_access(lines, line, character)

    local = flatten(document_symbols(path, source))
    pool: list[Symbol] = list(local)
    if workspace_symbols:
        pool.extend(workspace_symbols)

    items: dict[str, Completion] = {}

    if member_mode:
        for s in pool:
            if s.kind in _MEMBER_KINDS:
                items.setdefault(f"{s.kind.value}:{s.name}", _from_symbol(s))
        return list(items.values())

    for kw in KEYWORDS:
        items.setdefault("kw:" + kw, Completion(kw, "keyword", ""))
    for s in pool:
        if s.kind in _TOPLEVEL_KINDS:
            items.setdefault(f"{s.kind.value}:{s.name}", _from_symbol(s))
    return list(items.values())


def _from_symbol(s: Symbol) -> Completion:
    return Completion(label=s.name, kind=s.kind.value, detail=s.detail)


def _is_member_access(lines: list[str], line: int, character: int) -> bool:
    if line < 0 or line >= len(lines):
        return False
    text = lines[line]
    prefix = text[:from_lsp_character(text, character)]
    i = len(prefix)
    while i > 0 and (prefix[i - 1].isalnum() or prefix[i - 1] == "_"):
        i -= 1
    return i > 0 and prefix[i - 1] == "."
