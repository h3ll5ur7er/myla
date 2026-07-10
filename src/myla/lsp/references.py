"""Find All References for Myla source.

Name-based: every identifier token equal to the one under the cursor, across the
current buffer and — via an optional workspace resolver — every other `.my`
file. `include_declaration` optionally drops the declaration's own name token.
"""
from __future__ import annotations

import os
from typing import Callable

from .diagnostics import Location
from .lookup import identifier_at, identifier_ranges
from .symbols import document_symbols, flatten

# Maps a name to every cross-file occurrence (workspace index).
ReferenceResolver = Callable[[str], list[Location]]


def references_at(
    path: str,
    source: str,
    line: int,
    character: int,
    include_declaration: bool = True,
    resolver: ReferenceResolver | None = None,
) -> list[Location]:
    ident = identifier_at(source, line, character)
    if ident is None:
        return []

    locations: list[Location] = [
        Location(path=path, range=rng) for rng in identifier_ranges(source, ident)
    ]
    if resolver is not None:
        locations.extend(resolver(ident))

    # Deduplicate (the resolver may re-cover the current file).
    seen: set[tuple[str, object]] = set()
    unique: list[Location] = []
    for loc in locations:
        key = (os.path.realpath(loc.path), loc.range)
        if key in seen:
            continue
        seen.add(key)
        unique.append(loc)

    if not include_declaration:
        decl_ranges = {
            s.selection_range
            for s in flatten(document_symbols(path, source))
            if s.name == ident
        }
        here = os.path.realpath(path)
        unique = [
            loc
            for loc in unique
            if not (os.path.realpath(loc.path) == here and loc.range in decl_ranges)
        ]

    return unique
