"""A lightweight, workspace-wide symbol index for cross-file features.

Scans the workspace's `.my` files, extracting each file's top-level declarations
(via `symbols.document_symbols`) and caching them by modification time. Open,
possibly-unsaved editor buffers are passed in as overrides so the index always
reflects the text the user sees.

Everything is name-based (no type inference): it powers cross-file
go-to-definition, find-all-references, and workspace-aware completion.
"""
from __future__ import annotations

import os

from .diagnostics import Location, SourceRange
from .lookup import identifier_ranges
from .symbols import Symbol, SymbolKind, document_symbols

# Only these are worth indexing as jump targets / completions across files;
# fields and impl headers are intentionally excluded.
_INDEXABLE = {
    SymbolKind.FUNCTION,
    SymbolKind.STRUCT,
    SymbolKind.ENUM,
    SymbolKind.INTERFACE,
    SymbolKind.CONSTANT,
    SymbolKind.TYPE_ALIAS,
    SymbolKind.METHOD,
    SymbolKind.ENUM_MEMBER,
}


class Entry:
    __slots__ = ("name", "kind", "detail", "path", "range")

    def __init__(self, name: str, kind: SymbolKind, detail: str, path: str, rng: SourceRange):
        self.name = name
        self.kind = kind
        self.detail = detail
        self.path = path
        self.range = rng


class WorkspaceIndex:
    def __init__(self) -> None:
        self._roots: list[str] = []
        # path -> (mtime, entries) cache for files read from disk.
        self._cache: dict[str, tuple[float, list[Entry]]] = {}

    def set_roots(self, roots: list[str]) -> None:
        self._roots = [os.path.realpath(r) for r in roots if r]

    # -- file discovery -----------------------------------------------------

    def _iter_files(self) -> list[str]:
        seen: set[str] = set()
        files: list[str] = []
        for root in self._roots:
            for dirpath, dirnames, filenames in os.walk(root):
                # Skip common noise directories.
                dirnames[:] = [
                    d for d in dirnames
                    if d not in {".git", ".venv", "node_modules", "__pycache__", "build", "out"}
                ]
                for fn in filenames:
                    if fn.endswith(".my"):
                        p = os.path.realpath(os.path.join(dirpath, fn))
                        if p not in seen:
                            seen.add(p)
                            files.append(p)
        return files

    def _entries_for(self, path: str, overrides: dict[str, str]) -> list[Entry]:
        if path in overrides:
            # Live buffer: parse fresh, don't pollute the mtime cache.
            return _extract(path, overrides[path])
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return []
        cached = self._cache.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        try:
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
        except OSError:
            return []
        entries = _extract(path, source)
        self._cache[path] = (mtime, entries)
        return entries

    def _all_entries(self, overrides: dict[str, str]) -> list[Entry]:
        result: list[Entry] = []
        for path in self._iter_files():
            result.extend(self._entries_for(path, overrides))
        # Include open buffers that may not live under a root (e.g. untitled
        # saved elsewhere) — they were already covered if under a root.
        return result

    # -- queries ------------------------------------------------------------

    def _matches(self, name: str, overrides: dict[str, str]) -> list[Entry]:
        from .symbols import SYMBOL_PRIORITY

        matches = [e for e in self._all_entries(overrides) if e.name == name]
        matches.sort(key=lambda e: SYMBOL_PRIORITY.get(e.kind, 9))
        return matches

    def lookup(self, name: str, overrides: dict[str, str]) -> list[Location]:
        """Cross-file declaration locations for `name`, highest priority first."""
        return [Location(path=e.path, range=e.range) for e in self._matches(name, overrides)]

    def best_symbol(self, name: str, overrides: dict[str, str]) -> Symbol | None:
        """The highest-priority cross-file declaration for `name` as a `Symbol`
        (with empty children), or None."""
        matches = self._matches(name, overrides)
        return _entry_to_symbol(matches[0]) if matches else None

    def completion_symbols(self, overrides: dict[str, str]) -> list[Symbol]:
        """All indexable declarations across the workspace as `Symbol`s."""
        return [_entry_to_symbol(e) for e in self._all_entries(overrides)]

    def references(self, name: str, overrides: dict[str, str]) -> list[Location]:
        """Every identifier occurrence of `name` across all `.my` files."""
        out: list[Location] = []
        for path in self._iter_files():
            source = overrides.get(path)
            if source is None:
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        source = fh.read()
                except OSError:
                    continue
            for rng in identifier_ranges(source, name):
                out.append(Location(path=path, range=rng))
        return out


def _entry_to_symbol(e: Entry) -> Symbol:
    return Symbol(
        name=e.name, kind=e.kind, detail=e.detail,
        range=e.range, selection_range=e.range, children=[],
    )


def _extract(path: str, source: str) -> list[Entry]:
    entries: list[Entry] = []

    def walk(syms: list[Symbol]) -> None:
        for s in syms:
            if s.kind in _INDEXABLE:
                entries.append(Entry(s.name, s.kind, s.detail, path, s.selection_range))
            walk(s.children)

    walk(document_symbols(path, source))
    return entries
