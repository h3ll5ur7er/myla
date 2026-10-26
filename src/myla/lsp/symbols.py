"""Document symbols (outline) for Myla source.

Turns a single parsed file into a hierarchical `Symbol` tree that the language
server maps to LSP `DocumentSymbol`s. Only the file's own top-level
declarations are considered — no linking or type checking — so the outline keeps
working even when the program has type errors or unresolved imports; a *parse*
error simply yields no symbols (the diagnostics feature reports it).

Positions here are already 0-based / UTF-16 (LSP conventions); the conversion
uses `positions.to_lsp_position`, and ranges reuse `diagnostics.SourceRange`.
"""
from __future__ import annotations

import bisect
import dataclasses
import itertools
from dataclasses import dataclass, field
from enum import Enum

from .. import ast
from ..errors import MylaError
from ..lexer import tokenize
from ..parser import parse
from ..tokens import Token, TokenKind
from .diagnostics import SourceRange
from .positions import to_lsp_position


class SymbolKind(Enum):
    STRUCT = "struct"
    FUNCTION = "function"
    METHOD = "method"
    ENUM = "enum"
    ENUM_MEMBER = "enum_member"
    INTERFACE = "interface"
    IMPL = "impl"
    FIELD = "field"
    CONSTANT = "constant"
    TYPE_ALIAS = "type_alias"


@dataclass
class Symbol:
    name: str
    kind: SymbolKind
    detail: str
    range: SourceRange
    selection_range: SourceRange
    children: list["Symbol"]


# Lower number = preferred when a name matches several declarations (used by
# go-to-definition / hover to disambiguate a bare identifier).
SYMBOL_PRIORITY = {
    SymbolKind.FUNCTION: 0,
    SymbolKind.STRUCT: 0,
    SymbolKind.ENUM: 0,
    SymbolKind.INTERFACE: 0,
    SymbolKind.CONSTANT: 0,
    SymbolKind.TYPE_ALIAS: 0,
    SymbolKind.METHOD: 1,
    SymbolKind.ENUM_MEMBER: 1,
    SymbolKind.FIELD: 2,
    SymbolKind.IMPL: 3,
}


def flatten(symbols: list["Symbol"], out: list["Symbol"] | None = None) -> list["Symbol"]:
    """Depth-first flatten of a symbol tree into a single list."""
    if out is None:
        out = []
    for sym in symbols:
        out.append(sym)
        flatten(sym.children, out)
    return out


def best_match(symbols: list["Symbol"], name: str) -> "Symbol | None":
    """Return the highest-priority symbol named `name` in the tree, or None."""
    best: Symbol | None = None
    best_priority = 1 << 30
    for sym in flatten(symbols):
        if sym.name != name:
            continue
        priority = SYMBOL_PRIORITY.get(sym.kind, 9)
        if priority < best_priority:
            best_priority = priority
            best = sym
    return best


def document_symbols(path: str, source: str) -> list[Symbol]:
    """Parse `source` and return its top-level declarations as a symbol tree.

    Returns an empty list if the file cannot be lexed/parsed."""
    try:
        tokens = tokenize(source)
        program = parse(tokens)
    except MylaError:
        return []
    except Exception:  # noqa: BLE001 - never raise into the server
        return []

    doc = _Doc(source.splitlines(), tokens)
    symbols: list[Symbol] = []
    for decl in program.decls:
        sym = _decl_symbol(decl, doc)
        if sym is not None:
            symbols.append(sym)
    return symbols


@dataclass
class _Doc:
    """The document's lines and tokens (positions in the tokens are 1-based
    and count code points, as in the AST)."""
    lines: list[str]
    tokens: list[Token]
    keys: list[tuple[int, int]] = field(init=False)

    def __post_init__(self) -> None:
        self.keys = [(t.line, t.column) for t in self.tokens]


# --- declaration -> symbol -------------------------------------------------


def _decl_symbol(decl: ast.Node, doc: _Doc) -> Symbol | None:
    if isinstance(decl, ast.StructDecl):
        children = [
            _member_symbol(f, doc, SymbolKind.FIELD, detail=_type_str(f.type))
            for f in decl.fields
        ]
        return _make(decl, decl.name, SymbolKind.STRUCT, "struct", doc, children)

    if isinstance(decl, ast.EnumDecl):
        children = [
            _member_symbol(
                v, doc, SymbolKind.ENUM_MEMBER, detail=_variant_detail(v)
            )
            for v in decl.variants
        ]
        return _make(decl, decl.name, SymbolKind.ENUM, "enum", doc, children)

    if isinstance(decl, ast.TraitDecl):
        children = [_fun_symbol(m, doc) for m in decl.methods]
        return _make(
            decl, decl.name, SymbolKind.INTERFACE, "trait", doc, children
        )

    if isinstance(decl, ast.ImplDecl):
        target = _type_str(decl.target)
        children = [_fun_symbol(m, doc) for m in decl.methods]
        # the target is the last mention: `impl Tr<int32> for int32 {`
        return _make(
            decl, target, SymbolKind.IMPL, f"impl {target}", doc, children,
            name_for_selection=_type_head(decl.target), last=True,
        )

    if isinstance(decl, ast.FunDecl):
        return _fun_symbol(decl, doc)

    if isinstance(decl, ast.ConstDecl):
        return _make(
            decl, decl.name, SymbolKind.CONSTANT,
            _type_str(decl.declared_type), doc, [],
        )

    if isinstance(decl, ast.TypeAliasDecl):
        return _make(
            decl, decl.name, SymbolKind.TYPE_ALIAS,
            _type_str(decl.target), doc, [],
        )

    # ImportDecl and anything else are intentionally omitted from the outline.
    return None


def _fun_symbol(decl: ast.FunDecl, doc: _Doc) -> Symbol:
    kind = SymbolKind.METHOD if decl.receiver is not None else SymbolKind.FUNCTION
    return _make(decl, decl.name, kind, _fun_signature(decl), doc, [])


def _member_symbol(
    node: ast.Node, doc: _Doc, kind: SymbolKind, detail: str
) -> Symbol:
    name = getattr(node, "name", "")
    return _make(node, name, kind, detail, doc, [])


def _make(
    node: ast.Node,
    name: str,
    kind: SymbolKind,
    detail: str,
    doc: _Doc,
    children: list[Symbol],
    *,
    name_for_selection: str | None = None,
    last: bool = False,
) -> Symbol:
    start_line = node.line if node.line else 1
    start_col = node.column if node.column else 1

    full_start = to_lsp_position(doc.lines, start_line, start_col)
    end_line, end_col_1 = _subtree_end(node, start_line)
    full_end = to_lsp_position(doc.lines, end_line, end_col_1)
    full_range = SourceRange(full_start[0], full_start[1], full_end[0], full_end[1])

    selection = _name_range(doc, start_line, start_col, name_for_selection or name, last)
    if selection is None:
        selection = full_range if children == [] else SourceRange(*full_start, *full_start)

    return Symbol(
        name=name or "?",
        kind=kind,
        detail=detail,
        range=full_range,
        selection_range=selection,
        children=children,
    )


# --- range helpers ---------------------------------------------------------


def _name_range(doc: _Doc, line_1: int, col_1: int, name: str,
                last: bool = False) -> SourceRange | None:
    """The 0-based UTF-16 range of the first (with `last`, the last) token
    `name` in a declaration's header: from its start (the keyword, or the name
    of a field or variant) to `{`, `;` or the end of the line. Whole tokens
    only, so `fun un` never finds the `un` in `fun` (MYLA-48); a type name
    such as `int32` is a token of its own kind. None when there is none."""
    found = None
    i = bisect.bisect_left(doc.keys, (line_1, col_1))
    for tok in itertools.islice(doc.tokens, i, None):
        if tok.kind is TokenKind.NEWLINE and tok.line == line_1:
            continue                      # the previous line's (it starts this one)
        if tok.kind in (TokenKind.LBRACE, TokenKind.NEWLINE, TokenKind.SEMI, TokenKind.EOF):
            break
        if tok.lexeme == name:
            found = tok
            if not last:
                break
    if found is None:
        return None
    start = to_lsp_position(doc.lines, found.line, found.column)
    end = to_lsp_position(doc.lines, found.line, found.column + len(name))
    return SourceRange(start[0], start[1], end[0], end[1])


def _subtree_end(node: ast.Node, start_line: int) -> tuple[int, int]:
    """Return a best-effort end (1-based line, 1-based exclusive column) for a
    declaration by taking the last source line any descendant node touches and
    spanning to that line's end. AST nodes only carry start positions, so this
    approximates the body extent well enough for an outline."""
    max_line = _max_line(node, start_line)
    # We don't track line lengths here; the caller clamps via to_lsp_position,
    # so a large column is truncated to the actual end of the line.
    return (max_line, 1 << 30)


def _max_line(node, current: int) -> int:
    if isinstance(node, ast.Node):
        if getattr(node, "line", 0):
            current = max(current, node.line)
        for f in dataclasses.fields(node):
            current = _max_line(getattr(node, f.name), current)
    elif isinstance(node, (list, tuple)):
        for item in node:
            current = _max_line(item, current)
    return current


# --- detail / signature rendering ------------------------------------------


def _fun_signature(decl: ast.FunDecl) -> str:
    params = []
    if decl.receiver is not None:
        params.append(decl.receiver)  # "self" or "var self"
    params.extend(f"{p.name}: {_type_str(p.type)}" for p in decl.params)
    sig = f"fun {decl.name}({', '.join(params)})"
    if decl.ret_type is not None:
        sig += f" -> {_type_str(decl.ret_type)}"
    return sig


def _variant_detail(v: ast.Variant) -> str:
    if not v.payload:
        return ""
    return "(" + ", ".join(_type_str(t) for t in v.payload) + ")"


def _type_head(t) -> str:
    """The bare type name used to place the selection range for an impl."""
    if isinstance(t, ast.TypeRef):
        return t.name
    return _type_str(t)


def _type_str(t) -> str:
    if t is None:
        return "?"
    if isinstance(t, ast.TypeRef):
        if t.args:
            return f"{t.name}<{', '.join(_type_str(a) for a in t.args)}>"
        return t.name
    if isinstance(t, ast.TupleTypeRef):
        return "(" + ", ".join(_type_str(e) for e in t.elems) + ")"
    if isinstance(t, ast.ListTypeRef):
        return f"[{_type_str(t.elem)}]"
    if isinstance(t, ast.MapTypeRef):
        return f"[{_type_str(t.key)}: {_type_str(t.value)}]"
    if isinstance(t, ast.FnTypeRef):
        return (
            "(" + ", ".join(_type_str(p) for p in t.params) + ") -> "
            + _type_str(t.ret)
        )
    return "?"
