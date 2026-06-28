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
    # type arguments for a generic instantiation, e.g. `Box<int>` or
    # `Result<int, str>`; empty for a plain type name or a type parameter.
    args: list["TypeExpr"] = field(default_factory=list)


@dataclass
class TupleTypeRef(Node):
    """A tuple type annotation, e.g. `(int, str)` or the 1-tuple `(int,)`."""
    elems: list["TypeExpr"] = field(default_factory=list)


@dataclass
class ListTypeRef(Node):
    """A list type annotation `[T]` (D39); `elem` is the element type."""
    elem: "TypeExpr"


@dataclass
class MapTypeRef(Node):
    """A map type annotation `[K: V]` (D39): `key`/`value` element types."""
    key: "TypeExpr"
    value: "TypeExpr"


@dataclass
class FnTypeRef(Node):
    """A function-type annotation `(T0, T1, …) -> R` (v0.4.2). `params` may be
    empty (`() -> R`); `ret` is the result type."""
    params: list["TypeExpr"] = field(default_factory=list)
    ret: "TypeExpr" = None  # type: ignore[assignment]


# A type annotation as written in source (resolved to a `types.Type` later).
TypeExpr = Union[TypeRef, TupleTypeRef, ListTypeRef, MapTypeRef, FnTypeRef]


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
    is_char: bool = False  # a char literal `'a'`: defaults to uint8, still flexible


@dataclass
class FloatLit(Node):
    value: float
    suffix: Optional[str] = None  # "f32" / "f64" / None (unsuffixed)


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


@dataclass
class TupleLit(Node):
    elems: list["Expr"] = field(default_factory=list)


@dataclass
class TupleIndex(Node):
    target: "Expr"
    index: int


@dataclass
class ListLit(Node):
    """A list literal `[e0, e1, ...]` (D39); empty `[]` takes its element type
    from the expected type. The checker records the element type."""
    elems: list["Expr"] = field(default_factory=list)


@dataclass
class Index(Node):
    """A subscript `target[index]` — list element or map value access (read or
    lvalue). The checker resolves whether `target` is a list or a map."""
    target: "Expr"
    index: "Expr"


@dataclass
class MapLit(Node):
    """A map literal `[k0: v0, k1: v1, ...]` or the empty map `[:]` (D39); the
    checker records the key/value types. `entries` pairs key and value exprs."""
    entries: list[tuple["Expr", "Expr"]] = field(default_factory=list)


@dataclass
class Match(Node):
    scrutinee: "Expr"
    arms: list["MatchArm"] = field(default_factory=list)


@dataclass
class Try(Node):
    """Postfix `expr?` — early-return propagation for `Option`/`Result`.

    The checker validates the carrier and the enclosing return type, then
    records an equivalent `match` (built once the carrier is known) on
    `desugared`; a post-check pass rewrites the node away so the interpreter and
    compiler only ever see the desugared `match`.
    """
    operand: "Expr"


@dataclass
class Cast(Node):
    """`expr as T` — an explicit numeric conversion (D43).

    Only numeric-to-numeric casts are allowed; the checker validates the target
    and records it on `resolved_type`. Backends apply the source/target widths to
    sign- or zero-extend and truncate with wrapping semantics.
    """
    operand: "Expr"
    target: "TypeExpr"


@dataclass
class Lambda(Node):
    """An anonymous function value `(params) => body` (v0.4.2).

    `body` is either an `Expr` (its value is returned) or a `Block` (returns via
    `return`). Parameter types are required. The checker computes the set of
    captured outer variables (`captures`, a list of `(name, Type)` pairs,
    captured by value, D15) and assigns a unique lifted name used by the native
    backend's lambda-lifting pass.
    """
    params: list["Param"] = field(default_factory=list)
    body: "Union[Expr, Block]" = None  # type: ignore[assignment]
    ret_type: "Optional[TypeExpr]" = None
    # Filled in by the checker:
    captures: list = field(default_factory=list)  # list[(name, Type)]
    lifted_name: Optional[str] = None


@dataclass
class Hole(Node):
    """The `_` partial-application placeholder in a call argument (v0.4.3).

    A call carrying one or more holes desugars (in the checker) to a lambda
    whose parameters are the holes, left-to-right; the non-hole arguments are
    captured by value. `_` is only meaningful in call-argument position — the
    parser produces a `Hole` only there, and a bare `_` elsewhere is rejected.
    """


Expr = Union[
    IntLit, FloatLit, StrLit, BoolLit, Name, Unary, Binary, Call, FieldAccess,
    StructLit, TupleLit, TupleIndex, ListLit, MapLit, Index, Match, Try, Cast,
    Lambda, Hole,
]


# --- patterns (for `match` arms and, later, refutable bindings) -------------


@dataclass
class PatWildcard(Node):
    """`_` — matches anything, binds nothing."""


@dataclass
class PatBinding(Node):
    name: str  # binds the matched value; checker annotates `resolved_type`


@dataclass
class PatLiteral(Node):
    literal: "Expr"  # IntLit | StrLit | BoolLit (+ negative IntLit via Unary)


@dataclass
class PatEnum(Node):
    enum_name: Optional[str]  # `Color` in `Color.Red`; None for bare `.Red`/`Red`
    variant: str
    elems: list["Pattern"] = field(default_factory=list)
    has_payload_syntax: bool = False  # whether `(...)` was written


@dataclass
class PatTuple(Node):
    elems: list["Pattern"] = field(default_factory=list)


@dataclass
class FieldPat(Node):
    name: str
    pattern: "Pattern"


@dataclass
class PatStruct(Node):
    type_name: str
    fields: list[FieldPat] = field(default_factory=list)


@dataclass
class PatOr(Node):
    alts: list["Pattern"] = field(default_factory=list)


Pattern = Union[
    PatWildcard, PatBinding, PatLiteral, PatEnum, PatTuple, PatStruct, PatOr
]


@dataclass
class MatchArm(Node):
    pattern: Pattern
    guard: Optional["Expr"]
    body: Union["Expr", "Block"]


# --- statements ------------------------------------------------------------


@dataclass
class Block(Node):
    statements: list["Stmt"] = field(default_factory=list)


@dataclass
class VarDecl(Node):
    kind: str  # "let" or "var"
    name: str
    declared_type: Optional["TypeExpr"]
    init: "Expr"


# --- destructuring bindings ------------------------------------------------


@dataclass
class BindName(Node):
    name: str  # the binding identifier; the checker annotates `resolved_type`


@dataclass
class BindWildcard(Node):
    """The `_` element of a destructuring pattern — binds nothing."""


@dataclass
class BindTuple(Node):
    elems: list["BindElem"] = field(default_factory=list)


BindElem = Union[BindName, BindWildcard, BindTuple]


@dataclass
class DestructDecl(Node):
    """A `let`/`var` binding that destructures a tuple, e.g. `let (a, b) = t`."""
    kind: str  # "let" or "var"
    binding: BindTuple
    declared_type: Optional["TypeExpr"]
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
    """`for v in start..end { }` (range) or `for v in xs { }` (list iteration).

    Exactly one form is populated: a range has `start`/`end` set and `iterable`
    None; a list iteration has `iterable` set and `start`/`end` None.
    """
    var_name: str
    start: Optional["Expr"]
    end: Optional["Expr"]
    body: Block
    iterable: Optional["Expr"] = None


@dataclass
class Return(Node):
    value: Optional["Expr"] = None


@dataclass
class Break(Node):
    """`break` — exit the innermost enclosing loop."""


@dataclass
class Continue(Node):
    """`continue` — skip to the next iteration of the innermost enclosing loop."""


@dataclass
class ExprStmt(Node):
    expr: "Expr"


Stmt = Union[
    Block, VarDecl, DestructDecl, Assign, If, While, For, Return, Break,
    Continue, ExprStmt,
]


# --- declarations ----------------------------------------------------------


@dataclass
class Field(Node):
    name: str
    type: "TypeExpr"


@dataclass
class Param(Node):
    name: str
    type: "TypeExpr"


@dataclass
class StructDecl(Node):
    name: str
    fields: list[Field] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)
    type_params: list[str] = field(default_factory=list)
    # `pub` marks the declaration as part of its module's public surface (v0.5,
    # D22). False = file-local (the default).
    is_pub: bool = False


@dataclass
class FunDecl(Node):
    name: str
    params: list[Param]
    ret_type: Optional[TypeRef]
    # `None` for a trait method *signature* (v0.4.4) — a declaration without a
    # body; every other `fun`/method has a `Block`.
    body: Optional[Block]
    attributes: list[Attribute] = field(default_factory=list)
    type_params: list[str] = field(default_factory=list)
    # v0.4.4 (X9): single built-in-trait bounds per type parameter, e.g.
    # `<T: Add + Eq>` -> {"T": ["Add", "Eq"]}.
    type_param_bounds: dict = field(default_factory=dict)
    # For a method inside an `impl` block (v0.4.1): the receiver form, one of
    # "self" (read-only) or "var self" (mutating); None for a free function. The
    # `self` parameter is *not* listed in `params` — the checker synthesizes it
    # with the impl's target type.
    receiver: Optional[str] = None
    # `pub` export marker (v0.5, D22); ignored for methods inside an `impl`.
    is_pub: bool = False


@dataclass
class Variant(Node):
    name: str
    payload: list["TypeExpr"] = field(default_factory=list)


@dataclass
class EnumDecl(Node):
    name: str
    variants: list[Variant] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)
    type_params: list[str] = field(default_factory=list)
    is_pub: bool = False


@dataclass
class TypeAliasDecl(Node):
    name: str
    target: "TypeExpr"
    attributes: list[Attribute] = field(default_factory=list)
    is_pub: bool = False


@dataclass
class ImplDecl(Node):
    """An `impl` block attaching methods to a type (v0.4.1, D45/D46/D47).

    `target` is the type the methods are attached to (`impl Lexer { … }` or, for
    a generic impl, `impl<T> Box<T> { … }`). `type_params` are the impl's own
    type parameters. Each method is a `FunDecl` carrying a `receiver` of "self"
    or "var self". `trait_name` is reserved for `impl Trait for T` (v0.4.4) and
    is None for an inherent impl.
    """
    target: "TypeExpr"
    methods: list[FunDecl] = field(default_factory=list)
    type_params: list[str] = field(default_factory=list)
    type_param_bounds: dict = field(default_factory=dict)
    trait_name: Optional[str] = None
    # trait type arguments for `impl Comparable<int32> for T` (v0.5.5, D55);
    # empty for inherent impls and for non-generic traits.
    trait_args: list = field(default_factory=list)
    # impl blocks carry no attributes (the parser rejects them); this field
    # exists so passes that iterate every decl's `.attributes` need no special
    # case.
    attributes: list[Attribute] = field(default_factory=list)


@dataclass
class TraitDecl(Node):
    """A `trait` declaration (v0.4.4, D52): a named set of method *signatures*
    (no default bodies in v0.4). `Self` denotes the implementing type in the
    signatures. Methods are `FunDecl`s with `body=None` and a `self`/`var self`
    receiver. Traits live in their own namespace and are implemented for a type
    via `impl Trait for T { … }`."""
    name: str
    methods: list[FunDecl] = field(default_factory=list)
    type_params: list[str] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)
    is_pub: bool = False


@dataclass
class ConstDecl(Node):
    """A file-scoped, immutable compile-time constant (D28).

    The initializer must be a constant expression (literals, references to other
    `const`s, and arithmetic/bitwise/cast/logical operations over them); the
    checker folds it to a value and records it on `folded`.
    """
    name: str
    declared_type: "TypeExpr"
    value: "Expr"
    attributes: list[Attribute] = field(default_factory=list)
    is_pub: bool = False


@dataclass
class ImportPath(Node):
    """A dotted import path with a leading-dot search base (D22).

    `dots` is the leading-dot count selecting the search base: 0 = absolute
    (builtins / project root), 1 = the current file's directory, 2 = its parent,
    and so on. `segments` is the dotted path after the dots (always ≥ 1).
    """
    dots: int = 0
    segments: list[str] = field(default_factory=list)

    def dotted(self) -> str:
        return "." * self.dots + ".".join(self.segments)


@dataclass
class ImportItem(Node):
    """A single name in a `from … import a, b as c` list."""
    name: str
    alias: Optional[str] = None


@dataclass
class ImportDecl(Node):
    """An import statement (v0.5, D17/D22/D54).

    Two forms:
      * whole-module — `import a.b.c [as alias]`: `items` is None; `alias`
        optionally rebinds the full path to a simple name.
      * selective — `from a.b import x, y as z`: `items` is the non-empty list;
        `alias` is None.

    `is_pub` marks a `pub`-prefixed re-export (D54). A `pub` whole-module import
    requires an `as` alias (enforced by the parser).
    """
    path: ImportPath
    items: Optional[list[ImportItem]] = None
    alias: Optional[str] = None
    is_pub: bool = False
    attributes: list[Attribute] = field(default_factory=list)


Decl = Union[
    StructDecl, FunDecl, EnumDecl, TypeAliasDecl, ConstDecl, ImplDecl, TraitDecl,
    ImportDecl,
]


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
