"""Programs with one declaration error each, made from the examples (MYLA-110).

Each mutant takes a single-file example and breaks one declaration: a
parameter, return, field, payload, const, alias or impl target type becomes the
unknown type `Nope`, or a function, struct or enum is declared a second time.
The checker must report
that error first, and nothing that follows from it: the bodies that depend on
the broken part stop silently, the others are checked as before.

The declarations and their spans came from the Python parser; how it made the
mutants of each example is recorded (`tests/burn/_golden.py`, MYLA-219), so an
example that changes, or a new one, has none until it is recorded again.
"""
from __future__ import annotations

import glob
import os

from tests.burn._golden import golden

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

UNKNOWN = "Nope"


def _replace(src: str, span, text: str) -> str:
    """`src` with the range `span` (1-based lines and code-point columns, on
    one line) replaced by `text`."""
    sl, sc, el, ec = span
    lines = src.split("\n")
    line = lines[sl - 1]
    lines[sl - 1] = line[:sc - 1] + text + line[ec - 1:]
    return "\n".join(lines)


@golden("mutants.of_example")
def _example_edits(path: str) -> list[tuple[str, str, list, str]]:
    """How each mutant of the example `path` is made, as (name, edit, range,
    the first error's message): edit `type` replaces the one-line `range`
    (`_replace`) by the unknown type, `dup` repeats the lines `range`
    (first, last) after the last; none if the example does not parse or
    imports."""
    from myla import ast
    from myla.lexer import tokenize
    from myla.parser import parse

    def type_refs(decl) -> list:
        """The type annotations of `decl`'s signature or members."""
        refs = []
        if isinstance(decl, ast.FunDecl):
            refs += [p.type for p in decl.params if p.type is not None]
            if decl.ret_type is not None:
                refs.append(decl.ret_type)
        elif isinstance(decl, ast.StructDecl):
            refs += [f.type for f in decl.fields]
        elif isinstance(decl, ast.EnumDecl):
            for v in decl.variants:
                refs += list(v.payload)
        elif isinstance(decl, ast.ConstDecl):
            refs.append(decl.declared_type)
        elif isinstance(decl, ast.TypeAliasDecl):
            refs.append(decl.target)
        elif isinstance(decl, (ast.ImplDecl, ast.TraitDecl)):
            if isinstance(decl, ast.ImplDecl):
                refs.append(decl.target)
            for m in decl.methods:
                refs += type_refs(m)
        return [r for r in refs if r.span is not None and r.span[0] == r.span[2]]

    out = []
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    try:
        prog = parse(tokenize(src))
    except Exception:
        return out
    if any(isinstance(d, ast.ImportDecl) for d in prog.decls):
        return out
    base = os.path.basename(path)[:-3]
    for i, decl in enumerate(prog.decls):
        for j, ref in enumerate(type_refs(decl)):
            out.append((f"{base}_{i}_type{j}", "type", list(ref.span), f"unknown type '{UNKNOWN}'"))
        if isinstance(decl, (ast.FunDecl, ast.StructDecl, ast.EnumDecl)) and decl.span:
            sl, _, el, _ = decl.span
            out.append((f"{base}_{i}_dup", "dup", [sl, el], f"duplicate top-level declaration '{decl.name}'"))
    return out


def _mutate(src: str, edit: str, where: list) -> str:
    """`src` with the edit of `_example_edits` made."""
    if edit == "type":
        return _replace(src, where, UNKNOWN)
    lines = src.split("\n")
    sl, el = where
    copy = lines[sl - 1:el]
    return "\n".join(lines[:el] + copy + lines[el:])


def mutants() -> list[tuple[str, str, str]]:
    """(name, source, the first error's message) for every mutant."""
    out = []
    for path in sorted(glob.glob(os.path.join(_REPO, "examples", "*.my"))):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for name, edit, where, first in _example_edits(path):
            out.append((name, _mutate(src, edit, where), first))
    return out
