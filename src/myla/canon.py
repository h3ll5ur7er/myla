"""Canonical, cross-implementation dump formats (self-hosting, v0.6).

The self-hosted Myla toolchain is brought up stage by stage and validated by
*differential testing* against this Python oracle (see docs/Architecture/Self-hosted-compiler.md).
Comparing the Python debug reprs (e.g. ``Token.__str__``) is brittle — they lean
on Python ``repr`` escaping. Instead each stage emits a deliberately simple,
stable line format that is trivial to reproduce byte-for-byte in Myla.

Token line grammar (one token per line):

    KIND SP line SP col SP "<escaped-lexeme>"[ SP aux]* SP end=<line>:<col>

where ``aux`` carries only the fields the lexeme does not already determine:

    INT   -> int=<decimal>  [suf=<suffix>]
    FLOAT -> [suf=<suffix>]          (the lexeme already fixes the digits)
    CHAR  -> cp=<codepoint>

and ``end`` is where the token ends (MYLA-65).

The escaper handles just ``\\``, ``\n``, ``\t``, ``\r`` and ``"``; every other
byte (including multi-byte UTF-8) passes through verbatim, so a Myla port only
needs the same five rules over raw bytes.
"""
from __future__ import annotations

from .tokens import Token, TokenKind


def escape(s: str) -> str:
    """Escape a lexeme for the canonical dump (see module docstring)."""
    out: list[str] = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ch == '"':
            out.append('\\"')
        else:
            out.append(ch)
    return "".join(out)


def canonical_token(tok: Token) -> str:
    """One canonical line for a single token."""
    line = f'{tok.kind.name} {tok.line} {tok.column} "{escape(tok.lexeme)}"'
    aux: list[str] = []
    if tok.kind is TokenKind.INT:
        aux.append(f"int={tok.value}")
        if tok.suffix:
            aux.append(f"suf={tok.suffix}")
    elif tok.kind is TokenKind.FLOAT:
        if tok.suffix:
            aux.append(f"suf={tok.suffix}")
    elif tok.kind is TokenKind.CHAR:
        aux.append(f"cp={tok.value}")
    aux.append(f"end={tok.end_line}:{tok.end_column}")
    return line + " " + " ".join(aux)


def canonical_tokens(tokens: list[Token]) -> str:
    """The canonical dump of a whole token stream (one token per line)."""
    return "\n".join(canonical_token(t) for t in tokens)


def canonical_error(err) -> str:
    """A diagnostic as the self-hosted drivers print it:
    `err <line> <col> <span> <kind>: <message>`, the span `l:c-l:c` or `-`
    (MYLA-65), a missing position `-`, then a line for each of its notes."""
    line = "-" if err.line is None else str(err.line)
    col = "-" if err.column is None else str(err.column)
    span = "-" if err.span is None else "{}:{}-{}:{}".format(*err.span)
    out = f"err {line} {col} {span} {err.kind.split()[0]}: {err.message}"
    for n in err.notes:
        out += "\n" + canonical_note(n)
    return out


def canonical_warning(w) -> str:
    """A warning as the self-hosted drivers print it (D95): its
    `canonical_error` line with `warn` for `err`, then its notes."""
    return "warn" + canonical_error(w)[3:]


def canonical_note(n) -> str:
    """A note on an error as the self-hosted drivers print it, after the error
    (MYLA-65): `<label> <line> <col> <span>: <message>`, `-` for a missing
    position or span."""
    line = "-" if n.line is None else str(n.line)
    col = "-" if n.column is None else str(n.column)
    span = "-" if n.span is None else "{}:{}-{}:{}".format(*n.span)
    return f"{n.label} {line} {col} {span}: {n.message}"


def canonical_errors(err) -> str:
    """`err` and the errors in its `more` (MYLA-65, D80), one
    `canonical_error` line each: what the self-hosted drivers print for a
    run's errors."""
    return "\n".join(canonical_error(e) for e in (err, *err.more))


# --- canonical AST dump (self-hosting v0.6b) -------------------------------
#
# A compact one-line S-expression per node: `(tag child child ...)`. Lists are
# `[a b c]` (space-separated, empty `[]`); strings are `"<escaped>"`; ints are
# decimal; bools `true`/`false`; an absent optional is `nil`. The format is
# emitted explicitly per node (not reflectively) so the Myla port in
# selfhost/ast.py mirrors it arm-for-arm. It is *structural*: source positions
# are omitted (token parity already pins them down), and a float literal keeps
# only its suffix (its digits are gated at the token level), avoiding any
# float-formatting mismatch between implementations.

from . import ast as _ast


def _s(text) -> str:
    return '"' + escape(text) + '"'


def _opt_s(text) -> str:
    return "nil" if text is None else _s(text)


def _b(flag: bool) -> str:
    return "true" if flag else "false"


def _lst(items, fn) -> str:
    return "[" + " ".join(fn(it) for it in items) + "]"


def _tp(name: str, bounds) -> str:
    return "(tp " + _s(name) + " " + _lst(bounds, _s) + ")"


def _typarams(type_params, bounds_map) -> str:
    return _lst(
        [(n, bounds_map.get(n, [])) for n in type_params],
        lambda nb: _tp(nb[0], nb[1]),
    )


def _attr(a: "_ast.Attribute") -> str:
    outputs = "nil" if a.outputs is None else _lst(a.outputs, _ct)
    return "(attr " + _s(a.name) + " " + _lst(a.args, _ct) + " " + outputs + ")"


def _attrs(attrs) -> str:
    return _lst(attrs, _attr)


def _ct(node) -> str:
    """Canonical S-expression for one type / expr / pattern / stmt / decl node."""
    k = type(node).__name__

    # -- types --
    if k == "TypeRef":
        return "(tref " + _s(node.name) + " " + _lst(node.args, _ct) + ")"
    if k == "TupleTypeRef":
        return "(ttype " + _lst(node.elems, _ct) + ")"
    if k == "ListTypeRef":
        return "(ltype " + _ct(node.elem) + ")"
    if k == "MapTypeRef":
        return "(mtype " + _ct(node.key) + " " + _ct(node.value) + ")"
    if k == "FnTypeRef":
        ft = "(ftype " + _lst(node.params, _ct) + " " + _ct(node.ret) + ")"
        return "(async " + ft + ")" if node.is_async else ft

    # -- expressions --
    if k == "IntLit":
        return ("(int " + str(node.value) + " " + _opt_s(node.suffix)
                + " " + _b(node.is_char) + ")")
    if k == "FloatLit":
        return "(float " + _opt_s(node.suffix) + ")"
    if k == "StrLit":
        return "(str " + _s(node.value) + ")"
    if k == "BoolLit":
        return "(bool " + _b(node.value) + ")"
    if k == "Name":
        return "(name " + _s(node.ident) + ")"
    if k == "Await":
        return "(await " + _ct(node.operand) + ")"
    if k == "Unary":
        return "(unary " + _s(node.op) + " " + _ct(node.operand) + ")"
    if k == "Binary":
        return ("(binary " + _s(node.op) + " " + _ct(node.left)
                + " " + _ct(node.right) + ")")
    if k == "Call":
        return "(call " + _ct(node.callee) + " " + _lst(node.args, _ct) + ")"
    if k == "FieldAccess":
        return "(getfield " + _ct(node.target) + " " + _s(node.field_name) + ")"
    if k == "StructLit":
        return ("(structlit " + _s(node.type_name) + " "
                + _lst(node.fields, lambda f: "(finit " + _s(f.name) + " "
                       + _ct(f.value) + ")") + ")")
    if k == "TupleLit":
        return "(tuple " + _lst(node.elems, _ct) + ")"
    if k == "TupleIndex":
        return "(tindex " + _ct(node.target) + " " + str(node.index) + ")"
    if k == "ListLit":
        return "(list " + _lst(node.elems, _ct) + ")"
    if k == "MapLit":
        return ("(map " + _lst(node.entries, lambda kv: "(pair " + _ct(kv[0])
                + " " + _ct(kv[1]) + ")") + ")")
    if k == "Index":
        return "(index " + _ct(node.target) + " " + _ct(node.index) + ")"
    if k == "Match":
        return "(match " + _ct(node.scrutinee) + " " + _lst(node.arms, _arm) + ")"
    if k == "Try":
        return "(try " + _ct(node.operand) + ")"
    if k == "Cast":
        return "(cast " + _ct(node.operand) + " " + _ct(node.target) + ")"
    if k == "Lambda":
        ret = "nil" if node.ret_type is None else _ct(node.ret_type)
        lam = ("(lambda " + _lst(node.params, _param) + " " + ret
               + " " + _eb(node.body) + ")")
        return "(async " + lam + ")" if node.is_async else lam
    if k == "Hole":
        return "(hole)"

    # -- patterns --
    if k == "PatWildcard":
        return "(pwild)"
    if k == "PatBinding":
        return "(pbind " + _s(node.name) + ")"
    if k == "PatLiteral":
        return "(plit " + _ct(node.literal) + ")"
    if k == "PatEnum":
        return ("(penum " + _opt_s(node.enum_name) + " " + _s(node.variant)
                + " " + _lst(node.elems, _ct) + " "
                + _b(node.has_payload_syntax) + ")")
    if k == "PatTuple":
        return "(ptuple " + _lst(node.elems, _ct) + ")"
    if k == "PatStruct":
        return ("(pstruct " + _s(node.type_name) + " "
                + _lst(node.fields, lambda fp: "(fpat " + _s(fp.name) + " "
                       + _ct(fp.pattern) + ")") + ")")
    if k == "PatOr":
        return "(por " + _lst(node.alts, _ct) + ")"

    # -- bindings (destructuring) --
    if k == "BindName":
        return "(bname " + _s(node.name) + ")"
    if k == "BindWildcard":
        return "(bwild)"
    if k == "BindTuple":
        return "(btuple " + _lst(node.elems, _ct) + ")"

    # -- statements --
    if k == "Block":
        return "(block " + _lst(node.statements, _ct) + ")"
    if k == "VarDecl":
        ty = "nil" if node.declared_type is None else _ct(node.declared_type)
        return ("(vardecl " + _s(node.kind) + " " + _s(node.name) + " " + ty
                + " " + _ct(node.init) + ")")
    if k == "DestructDecl":
        ty = "nil" if node.declared_type is None else _ct(node.declared_type)
        return ("(destruct " + _s(node.kind) + " " + _ct(node.binding) + " "
                + ty + " " + _ct(node.init) + ")")
    if k == "Assign":
        return "(assign " + _ct(node.target) + " " + _ct(node.value) + ")"
    if k == "If":
        otherwise = "nil" if node.otherwise is None else _ct(node.otherwise)
        return ("(if " + _ct(node.cond) + " " + _ct(node.then) + " "
                + otherwise + ")")
    if k == "While":
        return "(while " + _ct(node.cond) + " " + _ct(node.body) + ")"
    if k == "For":
        start = "nil" if node.start is None else _ct(node.start)
        end = "nil" if node.end is None else _ct(node.end)
        iterable = "nil" if node.iterable is None else _ct(node.iterable)
        return ("(for " + _s(node.var_name) + " " + start + " " + end + " "
                + _ct(node.body) + " " + iterable + ")")
    if k == "Return" and node.tail:
        return "(become " + _ct(node.value) + ")"
    if k == "Return":
        return "(return " + ("nil" if node.value is None else _ct(node.value)) + ")"
    if k == "Break":
        return "(break)"
    if k == "Continue":
        return "(continue)"
    if k == "ExprStmt":
        return "(exprstmt " + _ct(node.expr) + ")"

    # -- declarations --
    if k == "StructDecl":
        return ("(" + ("actor " if node.actor else "struct ") + _s(node.name) + " "
                + _lst(node.fields, lambda f: "(field " + _s(f.name) + " "
                       + _ct(f.type) + ")") + " " + _attrs(node.attributes) + " "
                + _typarams(node.type_params, {}) + " " + _b(node.is_pub) + ")")
    if k == "FunDecl":
        return _fun(node)
    if k == "EnumDecl":
        return ("(enum " + _s(node.name) + " "
                + _lst(node.variants, lambda v: "(variant " + _s(v.name) + " "
                       + _lst(v.payload, _ct) + ")") + " "
                + _attrs(node.attributes) + " "
                + _typarams(node.type_params, {}) + " " + _b(node.is_pub) + ")")
    if k == "TypeAliasDecl":
        return ("(typealias " + _s(node.name) + " " + _ct(node.target) + " "
                + _attrs(node.attributes) + " " + _b(node.is_pub) + ")")
    if k == "ImplDecl":
        return ("(impl " + _ct(node.target) + " " + _lst(node.methods, _fun)
                + " " + _typarams(node.type_params, node.type_param_bounds) + " "
                + _opt_s(node.trait_name) + " " + _lst(node.trait_args, _ct) + ")")
    if k == "TraitDecl":
        return ("(trait " + _s(node.name) + " " + _lst(node.methods, _fun) + " "
                + _typarams(node.type_params, {}) + " " + _b(node.is_pub) + ")")
    if k == "ConstDecl":
        return ("(const " + _s(node.name) + " " + _ct(node.declared_type) + " "
                + _ct(node.value) + " " + _attrs(node.attributes) + " "
                + _b(node.is_pub) + ")")
    if k == "ImportDecl":
        path = ("(ipath " + str(node.path.dots) + " "
                + _lst(node.path.segments, _s) + ")")
        items = ("nil" if node.items is None
                 else _lst(node.items, lambda it: "(iitem " + _s(it.name) + " "
                           + _opt_s(it.alias) + ")"))
        return ("(import " + path + " " + items + " " + _opt_s(node.alias) + " "
                + _b(node.is_pub) + ")")
    if k == "Program":
        return "(program " + _lst(node.decls, _ct) + ")"

    raise AssertionError(f"canonical_ast: unhandled node {k}")


def _param(p: "_ast.Param") -> str:
    ty = "nil" if p.type is None else _ct(p.type)
    return "(param " + _s(p.name) + " " + ty + ")"


def _arm(a: "_ast.MatchArm") -> str:
    guard = "nil" if a.guard is None else _ct(a.guard)
    return "(arm " + _ct(a.pattern) + " " + guard + " " + _eb(a.body) + ")"


def _eb(body) -> str:
    """An expr-or-block body (lambda / match arm): blocks dump as their own node,
    so no wrapper tag is needed."""
    return _ct(body)


def _fun(node: "_ast.FunDecl") -> str:
    ret = "nil" if node.ret_type is None else _ct(node.ret_type)
    body = "nil" if node.body is None else _ct(node.body)
    return (("(async-fun " if node.is_async else "(fun ") + _s(node.name) + " " + _lst(node.params, _param) + " "
            + ret + " " + body + " " + _attrs(node.attributes) + " "
            + _typarams(node.type_params, node.type_param_bounds) + " "
            + _opt_s(node.receiver) + " " + _b(node.is_pub) + ")")


def canonical_ast(program: "_ast.Program") -> str:
    """Canonical one-line-per-construct S-expression dump of a parsed Program.

    The top level prints one declaration per line (so diffs localize), each a
    self-contained S-expression."""
    return "\n".join(_ct(d) for d in program.decls)
