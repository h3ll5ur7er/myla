"""Abstract syntax tree node definitions for Myla v0.0.

One dataclass per grammar construct (see docs/architecture.md §4 and
docs/grammar.md §2). Every node inherits from `Node`, which provides optional
1-based `line`/`column` source positions. Positions are stored as plain
attributes (not dataclass fields), so they are excluded from equality and repr —
this lets tests compare ASTs structurally without caring about positions.

Type annotations are represented uniformly as `TypeRef(name)`; resolving aliases
(including the built-in `int` = `int32`) and validating names is the type
checker's job, not the parser's.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


class Node:
    """Base class for all AST nodes; carries an optional source position."""

    line: int = 0
    column: int = 0

    def at(self, line: int, column: int):
        self.line = line
        self.column = column
        return self


# --- types -----------------------------------------------------------------


@dataclass
class TypeRef(Node):
    name: str


# --- attributes ------------------------------------------------------------


@dataclass
class Attribute(Node):
    name: str
    args: list["Expr"] = field(default_factory=list)
    # `outputs` is None when no `[...]` is present, else the bracketed list.
    outputs: Optional[list["Expr"]] = None


# --- expressions -----------------------------------------------------------


@dataclass
class IntLit(Node):
    value: int
    suffix: Optional[str] = None


@dataclass
class StrLit(Node):
    value: str


@dataclass
class BoolLit(Node):
    value: bool


@dataclass
class Name(Node):
    ident: str


@dataclass
class Unary(Node):
    op: str
    operand: "Expr"


@dataclass
class Binary(Node):
    op: str
    left: "Expr"
    right: "Expr"


@dataclass
class Call(Node):
    callee: "Expr"
    args: list["Expr"] = field(default_factory=list)


@dataclass
class FieldAccess(Node):
    target: "Expr"
    field_name: str


@dataclass
class FieldInit(Node):
    name: str
    value: "Expr"


@dataclass
class StructLit(Node):
    type_name: str
    fields: list[FieldInit] = field(default_factory=list)


Expr = Union[
    IntLit, StrLit, BoolLit, Name, Unary, Binary, Call, FieldAccess, StructLit
]


# --- statements ------------------------------------------------------------


@dataclass
class Block(Node):
    statements: list["Stmt"] = field(default_factory=list)


@dataclass
class VarDecl(Node):
    kind: str  # "let" or "var"
    name: str
    declared_type: Optional[TypeRef]
    init: "Expr"


@dataclass
class Assign(Node):
    target: "Expr"  # Name or FieldAccess chain (an lvalue)
    value: "Expr"


@dataclass
class If(Node):
    cond: "Expr"
    then: Block
    otherwise: Optional[Union[Block, "If"]] = None


@dataclass
class While(Node):
    cond: "Expr"
    body: Block


@dataclass
class For(Node):
    var_name: str
    start: "Expr"
    end: "Expr"
    body: Block


@dataclass
class Return(Node):
    value: Optional["Expr"] = None


@dataclass
class ExprStmt(Node):
    expr: "Expr"


Stmt = Union[Block, VarDecl, Assign, If, While, For, Return, ExprStmt]


# --- declarations ----------------------------------------------------------


@dataclass
class Field(Node):
    name: str
    type: TypeRef


@dataclass
class Param(Node):
    name: str
    type: TypeRef


@dataclass
class StructDecl(Node):
    name: str
    fields: list[Field] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)


@dataclass
class FunDecl(Node):
    name: str
    params: list[Param]
    ret_type: Optional[TypeRef]
    body: Block
    attributes: list[Attribute] = field(default_factory=list)


@dataclass
class TypeAliasDecl(Node):
    name: str
    target: TypeRef
    attributes: list[Attribute] = field(default_factory=list)


Decl = Union[StructDecl, FunDecl, TypeAliasDecl]


@dataclass
class Program(Node):
    decls: list[Decl] = field(default_factory=list)


# --- pretty-printer --------------------------------------------------------


def format_ast(node, indent: int = 0) -> str:
    """Render an AST node as an indented, human-readable tree (for debugging)."""
    import dataclasses

    pad = "  " * indent

    if isinstance(node, Node):
        fields = dataclasses.fields(node)
        if not fields:
            return f"{type(node).__name__}"
        lines = [f"{type(node).__name__}"]
        for f in fields:
            val = getattr(node, f.name)
            lines.append(f"{pad}  {f.name}: {format_ast(val, indent + 1)}")
        return "\n".join(lines)

    if isinstance(node, list):
        if not node:
            return "[]"
        lines = ["["]
        for item in node:
            lines.append(f"{pad}  - {format_ast(item, indent + 1)}")
        lines.append(f"{pad}]")
        return "\n".join(lines)

    return repr(node)
