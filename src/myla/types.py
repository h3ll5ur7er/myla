"""Type representations and the static type checker for Myla v0.0.

The checker (docs/architecture.md §5) runs after parsing and before
interpretation/compilation. It:

- builds global tables of structs, functions, and type aliases (order
  independent), resolving the built-in `int` = `int32` alias and user
  `typealias` declarations (with cycle detection);
- validates the `#main` / `#test` attributes;
- type-checks every function body, annotating each value expression with a
  `resolved_type` attribute that the interpreter and compiler rely on.

Integer literals are "flexible": an unsuffixed literal adopts the type required
by its context (annotation, parameter, return, or the other operand of a binary
op), defaulting to `int` (`int32`).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ast
from .errors import TypeCheckError


# --- type representations --------------------------------------------------


class Type:
    pass


@dataclass(frozen=True)
class IntType(Type):
    width: int   # 8, 16, 32, 64
    signed: bool


@dataclass(frozen=True)
class BoolType(Type):
    pass


@dataclass(frozen=True)
class StrType(Type):
    pass


@dataclass(frozen=True)
class StructType(Type):
    name: str


BOOL = BoolType()
STR = StrType()

# primitive type-name keyword -> Type
_PRIMITIVES: dict[str, Type] = {
    "bool": BOOL,
    "str": STR,
    "int8": IntType(8, True),
    "int16": IntType(16, True),
    "int32": IntType(32, True),
    "int64": IntType(64, True),
    "uint8": IntType(8, False),
    "uint16": IntType(16, False),
    "uint32": IntType(32, False),
    "uint64": IntType(64, False),
}

# integer literal suffix -> Type
_SUFFIX_TYPES: dict[str, Type] = {
    "i8": IntType(8, True), "i16": IntType(16, True),
    "i32": IntType(32, True), "i64": IntType(64, True),
    "u8": IntType(8, False), "u16": IntType(16, False),
    "u32": IntType(32, False), "u64": IntType(64, False),
}

INT = IntType(32, True)  # what `int` aliases


def type_name(t: Type | None) -> str:
    if t is None:
        return "()"
    if isinstance(t, IntType):
        return f"{'int' if t.signed else 'uint'}{t.width}"
    if isinstance(t, BoolType):
        return "bool"
    if isinstance(t, StrType):
        return "str"
    if isinstance(t, StructType):
        return t.name
    return str(t)


def int_fits(value: int, t: IntType) -> bool:
    """Whether a non-negative literal magnitude fits `t`.

    For signed types we permit the magnitude up to 2**(width-1) so that a
    negated literal like `-128i8` is accepted (the unary minus is a separate
    node). This is intentionally permissive, matching the wrapping semantics.
    """
    if t.signed:
        return 0 <= value <= (1 << (t.width - 1))
    return 0 <= value <= (1 << t.width) - 1


@dataclass
class FuncSig:
    params: list[Type]
    ret: Type | None
    decl: ast.FunDecl


@dataclass
class _Binding:
    type: Type
    mutable: bool


class _Scope:
    def __init__(self, parent: "_Scope | None" = None):
        self.parent = parent
        self.names: dict[str, _Binding] = {}

    def define(self, name: str, binding: _Binding) -> bool:
        if name in self.names:
            return False
        self.names[name] = binding
        return True

    def lookup(self, name: str) -> _Binding | None:
        scope: _Scope | None = self
        while scope is not None:
            if name in scope.names:
                return scope.names[name]
            scope = scope.parent
        return None


# names that may not be used as user declarations
_BUILTIN_FUNCS = {"print"}


class Checker:
    def __init__(self, program: ast.Program):
        self.program = program
        self.structs: dict[str, dict[str, Type]] = {}
        self.struct_decls: dict[str, ast.StructDecl] = {}
        self.functions: dict[str, FuncSig] = {}
        self._aliases_raw: dict[str, ast.TypeRef] = {}
        self._alias_cache: dict[str, Type] = {}
        self.entry: ast.FunDecl | None = None

    # -- public entry --------------------------------------------------------

    def check(self) -> "Checker":
        self._collect_globals()
        self._resolve_signatures()
        self._check_attributes_and_entry()
        for decl in self.program.decls:
            if isinstance(decl, ast.FunDecl):
                self._check_function(decl)
        return self

    # -- global collection ---------------------------------------------------

    def _collect_globals(self) -> None:
        seen: dict[str, ast.Node] = {}
        for decl in self.program.decls:
            name = decl.name
            if name in _BUILTIN_FUNCS:
                raise TypeCheckError(
                    f"cannot redefine builtin '{name}'", decl.line, decl.column
                )
            if name in seen:
                raise TypeCheckError(
                    f"duplicate top-level declaration '{name}'", decl.line, decl.column
                )
            seen[name] = decl
            if isinstance(decl, ast.StructDecl):
                self.struct_decls[name] = decl
                self.structs[name] = {}  # filled during resolution
            elif isinstance(decl, ast.TypeAliasDecl):
                self._aliases_raw[name] = decl.target
            elif isinstance(decl, ast.FunDecl):
                self.functions[name] = FuncSig([], None, decl)  # filled later

    def _resolve_signatures(self) -> None:
        # resolve every alias eagerly so cycles / bad targets are caught even
        # when the alias is never referenced
        for name, ref in self._aliases_raw.items():
            self._resolve(ref, frozenset({name}))
        # struct fields
        for name, decl in self.struct_decls.items():
            fields: dict[str, Type] = {}
            for f in decl.fields:
                if f.name in fields:
                    raise TypeCheckError(
                        f"duplicate field '{f.name}' in struct '{name}'", f.line, f.column
                    )
                fields[f.name] = self._resolve(f.type)
            self.structs[name] = fields
        # function signatures
        for name, sig in self.functions.items():
            decl = sig.decl
            params = [self._resolve(p.type) for p in decl.params]
            ret = self._resolve(decl.ret_type) if decl.ret_type is not None else None
            self.functions[name] = FuncSig(params, ret, decl)

    def _resolve(self, ref: ast.TypeRef, visiting: frozenset[str] = frozenset()) -> Type:
        name = ref.name
        if name in _PRIMITIVES:
            return _PRIMITIVES[name]
        if name in self._aliases_raw:
            if name in self._alias_cache:
                return self._alias_cache[name]
            if name in visiting:
                raise TypeCheckError(f"type alias cycle involving '{name}'", ref.line, ref.column)
            resolved = self._resolve(self._aliases_raw[name], visiting | {name})
            self._alias_cache[name] = resolved
            return resolved
        if name == "int":
            return INT
        if name in self.structs:
            return StructType(name)
        raise TypeCheckError(f"unknown type '{name}'", ref.line, ref.column)

    # -- attributes & entry point -------------------------------------------

    def _check_attributes_and_entry(self) -> None:
        main_decls: list[ast.FunDecl] = []
        for decl in self.program.decls:
            for attr in decl.attributes:
                if attr.name not in ("main", "test"):
                    raise TypeCheckError(
                        f"unknown attribute '#{attr.name}'", attr.line, attr.column
                    )
                if not isinstance(decl, ast.FunDecl):
                    raise TypeCheckError(
                        f"attribute '#{attr.name}' may only be applied to functions",
                        attr.line, attr.column,
                    )
                if attr.name == "main":
                    self._check_main_attr(decl, attr)
                    main_decls.append(decl)
                else:
                    self._check_test_attr(decl, attr)

        named_main = self.functions.get("main")
        if main_decls and named_main is not None and named_main.decl not in main_decls:
            raise TypeCheckError(
                "both a '#main' function and a function named 'main' are present",
                named_main.decl.line, named_main.decl.column,
            )
        if len(main_decls) > 1:
            raise TypeCheckError(
                "more than one '#main' entry point", main_decls[1].line, main_decls[1].column
            )
        entry = main_decls[0] if main_decls else (named_main.decl if named_main else None)
        if entry is not None and entry.params:
            raise TypeCheckError(
                "entry point must take no parameters in v0.0", entry.line, entry.column
            )
        self.entry = entry

    def _check_main_attr(self, decl: ast.FunDecl, attr: ast.Attribute) -> None:
        if attr.args or attr.outputs is not None:
            raise TypeCheckError("'#main' takes no arguments", attr.line, attr.column)

    def _check_test_attr(self, decl: ast.FunDecl, attr: ast.Attribute) -> None:
        sig = self.functions[decl.name]
        if attr.outputs is None:
            raise TypeCheckError(
                "'#test' requires an expected result, e.g. #test(args)[expected]",
                attr.line, attr.column,
            )
        if sig.ret is None:
            raise TypeCheckError(
                "'#test' requires the function to return a value", attr.line, attr.column
            )
        if len(attr.args) != len(sig.params):
            raise TypeCheckError(
                f"'#test' expects {len(sig.params)} argument(s), got {len(attr.args)}",
                attr.line, attr.column,
            )
        for arg, ptype in zip(attr.args, sig.params):
            self._expect_value(arg, _Scope(), ptype)
        if len(attr.outputs) != 1:
            raise TypeCheckError(
                "'#test' expects exactly one expected value in [...]", attr.line, attr.column
            )
        self._expect_value(attr.outputs[0], _Scope(), sig.ret)

    # -- function bodies -----------------------------------------------------

    def _check_function(self, decl: ast.FunDecl) -> None:
        sig = self.functions[decl.name]
        scope = _Scope()
        for param, ptype in zip(decl.params, sig.params):
            scope.define(param.name, _Binding(ptype, mutable=False))
        self._check_block(decl.body, scope, sig.ret)
        if sig.ret is not None and not _block_returns(decl.body):
            raise TypeCheckError(
                f"function '{decl.name}' may finish without returning a "
                f"'{type_name(sig.ret)}'",
                decl.line, decl.column,
            )

    def _check_block(self, block: ast.Block, parent: _Scope, ret: Type | None) -> None:
        scope = _Scope(parent)
        for stmt in block.statements:
            self._check_stmt(stmt, scope, ret)

    def _check_stmt(self, stmt: ast.Stmt, scope: _Scope, ret: Type | None) -> None:
        if isinstance(stmt, ast.VarDecl):
            declared = self._resolve(stmt.declared_type) if stmt.declared_type else None
            value_type = self._expect_value(stmt.init, scope, declared)
            final = declared if declared is not None else value_type
            if declared is not None and value_type != declared:
                raise TypeCheckError(
                    f"cannot assign value of type '{type_name(value_type)}' to "
                    f"binding of type '{type_name(declared)}'",
                    stmt.line, stmt.column,
                )
            if not scope.define(stmt.name, _Binding(final, mutable=(stmt.kind == "var"))):
                raise TypeCheckError(
                    f"'{stmt.name}' is already declared in this scope", stmt.line, stmt.column
                )

        elif isinstance(stmt, ast.Assign):
            target_type, mutable = self._check_lvalue(stmt.target, scope)
            if not mutable:
                raise TypeCheckError(
                    "cannot assign to an immutable binding (declare it with 'var')",
                    stmt.line, stmt.column,
                )
            value_type = self._expect_value(stmt.value, scope, target_type)
            if value_type != target_type:
                raise TypeCheckError(
                    f"cannot assign '{type_name(value_type)}' to '{type_name(target_type)}'",
                    stmt.line, stmt.column,
                )

        elif isinstance(stmt, ast.If):
            self._expect_type(stmt.cond, scope, BOOL, "if condition")
            self._check_block(stmt.then, scope, ret)
            if isinstance(stmt.otherwise, ast.If):
                self._check_stmt(stmt.otherwise, scope, ret)
            elif isinstance(stmt.otherwise, ast.Block):
                self._check_block(stmt.otherwise, scope, ret)

        elif isinstance(stmt, ast.While):
            self._expect_type(stmt.cond, scope, BOOL, "while condition")
            self._check_block(stmt.body, scope, ret)

        elif isinstance(stmt, ast.For):
            start_t = self._expect_value(stmt.start, scope, None)
            end_t = self._expect_value(stmt.end, scope, None)
            loop_t = self._unify(stmt.start, start_t, stmt.end, end_t)
            if not isinstance(loop_t, IntType):
                raise TypeCheckError("for-range bounds must be integers", stmt.line, stmt.column)
            body_scope = _Scope(scope)
            body_scope.define(stmt.var_name, _Binding(loop_t, mutable=False))
            self._check_block(stmt.body, body_scope, ret)

        elif isinstance(stmt, ast.Return):
            if ret is None:
                if stmt.value is not None:
                    raise TypeCheckError(
                        "cannot return a value from a function with no return type",
                        stmt.line, stmt.column,
                    )
            else:
                if stmt.value is None:
                    raise TypeCheckError(
                        f"expected a return value of type '{type_name(ret)}'",
                        stmt.line, stmt.column,
                    )
                vt = self._expect_value(stmt.value, scope, ret)
                if vt != ret:
                    raise TypeCheckError(
                        f"return type mismatch: expected '{type_name(ret)}', "
                        f"found '{type_name(vt)}'",
                        stmt.line, stmt.column,
                    )

        elif isinstance(stmt, ast.ExprStmt):
            self._infer(stmt.expr, scope, None)  # void calls allowed here

        else:  # pragma: no cover - defensive
            raise TypeCheckError(f"unsupported statement {type(stmt).__name__}",
                                 stmt.line, stmt.column)

    def _check_lvalue(self, expr: ast.Expr, scope: _Scope) -> tuple[Type, bool]:
        if isinstance(expr, ast.Name):
            binding = scope.lookup(expr.ident)
            if binding is None:
                raise TypeCheckError(f"unknown name '{expr.ident}'", expr.line, expr.column)
            expr.resolved_type = binding.type
            return binding.type, binding.mutable
        if isinstance(expr, ast.FieldAccess):
            base_type, mutable = self._check_lvalue(expr.target, scope)
            if not isinstance(base_type, StructType):
                raise TypeCheckError(
                    f"type '{type_name(base_type)}' has no fields", expr.line, expr.column
                )
            fields = self.structs[base_type.name]
            if expr.field_name not in fields:
                raise TypeCheckError(
                    f"struct '{base_type.name}' has no field '{expr.field_name}'",
                    expr.line, expr.column,
                )
            ft = fields[expr.field_name]
            expr.resolved_type = ft
            return ft, mutable
        raise TypeCheckError("invalid assignment target", expr.line, expr.column)

    # -- expression typing ---------------------------------------------------

    def _expect_type(self, expr: ast.Expr, scope: _Scope, want: Type, ctx: str) -> None:
        t = self._expect_value(expr, scope, want)
        if t != want:
            raise TypeCheckError(
                f"{ctx} must be '{type_name(want)}', found '{type_name(t)}'",
                expr.line, expr.column,
            )

    def _expect_value(self, expr: ast.Expr, scope: _Scope, expected: Type | None) -> Type:
        t = self._infer(expr, scope, expected)
        if t is None:
            raise TypeCheckError("expression does not produce a value", expr.line, expr.column)
        return t

    def _infer(self, expr: ast.Expr, scope: _Scope, expected: Type | None) -> Type | None:
        if isinstance(expr, ast.IntLit):
            return self._infer_int_lit(expr, expected)
        if isinstance(expr, ast.StrLit):
            expr.resolved_type = STR
            return STR
        if isinstance(expr, ast.BoolLit):
            expr.resolved_type = BOOL
            return BOOL
        if isinstance(expr, ast.Name):
            return self._infer_name(expr, scope)
        if isinstance(expr, ast.Unary):
            return self._infer_unary(expr, scope, expected)
        if isinstance(expr, ast.Binary):
            return self._infer_binary(expr, scope, expected)
        if isinstance(expr, ast.Call):
            return self._infer_call(expr, scope)
        if isinstance(expr, ast.FieldAccess):
            return self._infer_field(expr, scope)
        if isinstance(expr, ast.StructLit):
            return self._infer_struct_lit(expr, scope)
        raise TypeCheckError(  # pragma: no cover - defensive
            f"unsupported expression {type(expr).__name__}", expr.line, expr.column
        )

    def _infer_int_lit(self, expr: ast.IntLit, expected: Type | None) -> Type:
        if expr.suffix is not None:
            t = _SUFFIX_TYPES[expr.suffix]
        elif isinstance(expected, IntType):
            t = expected
        else:
            t = INT
        assert isinstance(t, IntType)
        if not int_fits(expr.value, t):
            raise TypeCheckError(
                f"integer literal {expr.value} does not fit in '{type_name(t)}'",
                expr.line, expr.column,
            )
        expr.resolved_type = t
        return t

    def _infer_name(self, expr: ast.Name, scope: _Scope) -> Type:
        binding = scope.lookup(expr.ident)
        if binding is None:
            if expr.ident in self.functions or expr.ident in _BUILTIN_FUNCS:
                raise TypeCheckError(
                    f"'{expr.ident}' is a function and cannot be used as a value in v0.0",
                    expr.line, expr.column,
                )
            raise TypeCheckError(f"unknown name '{expr.ident}'", expr.line, expr.column)
        expr.resolved_type = binding.type
        return binding.type

    def _infer_unary(self, expr: ast.Unary, scope: _Scope, expected: Type | None) -> Type:
        if expr.op == "-":
            t = self._expect_value(expr.operand, scope, expected if isinstance(expected, IntType) else None)
            if not isinstance(t, IntType):
                raise TypeCheckError("unary '-' requires an integer", expr.line, expr.column)
            expr.resolved_type = t
            return t
        if expr.op == "!":
            self._expect_type(expr.operand, scope, BOOL, "operand of '!'")
            expr.resolved_type = BOOL
            return BOOL
        raise TypeCheckError(f"unknown unary operator '{expr.op}'", expr.line, expr.column)

    def _infer_binary(self, expr: ast.Binary, scope: _Scope, expected: Type | None) -> Type:
        op = expr.op
        if op in ("&&", "||"):
            self._expect_type(expr.left, scope, BOOL, f"operand of '{op}'")
            self._expect_type(expr.right, scope, BOOL, f"operand of '{op}'")
            expr.resolved_type = BOOL
            return BOOL

        if op in ("==", "!="):
            lt = self._expect_value(expr.left, scope, None)
            rt = self._expect_value(expr.right, scope, lt if isinstance(lt, IntType) else None)
            common = self._unify(expr.left, lt, expr.right, rt)
            if not isinstance(common, (IntType, BoolType, StrType)):
                raise TypeCheckError(
                    f"cannot compare values of type '{type_name(common)}'",
                    expr.line, expr.column,
                )
            expr.resolved_type = BOOL
            return BOOL

        if op in ("<", "<=", ">", ">="):
            lt = self._expect_value(expr.left, scope, None)
            rt = self._expect_value(expr.right, scope, lt if isinstance(lt, IntType) else None)
            common = self._unify(expr.left, lt, expr.right, rt)
            if not isinstance(common, IntType):
                raise TypeCheckError("comparison requires integers", expr.line, expr.column)
            expr.resolved_type = BOOL
            return BOOL

        # arithmetic: + - * / %
        hint = expected if isinstance(expected, IntType) else None
        lt = self._expect_value(expr.left, scope, hint)
        rt = self._expect_value(expr.right, scope, lt if isinstance(lt, IntType) else hint)
        common = self._unify(expr.left, lt, expr.right, rt)
        if not isinstance(common, IntType):
            raise TypeCheckError(
                f"operator '{op}' requires integer operands", expr.line, expr.column
            )
        expr.resolved_type = common
        return common

    def _unify(self, ln: ast.Expr, lt: Type, rn: ast.Expr, rt: Type) -> Type:
        if lt == rt:
            return lt
        if isinstance(lt, IntType) and isinstance(rt, IntType):
            if _is_flexible_int_lit(ln):
                lt = self._infer_int_lit(ln, rt)  # adopt rt
            elif _is_flexible_int_lit(rn):
                rt = self._infer_int_lit(rn, lt)  # adopt lt
            if lt == rt:
                return lt
        raise TypeCheckError(
            f"type mismatch: '{type_name(lt)}' vs '{type_name(rt)}' "
            "(no implicit conversion between integer types)",
            ln.line, ln.column,
        )

    def _infer_call(self, expr: ast.Call, scope: _Scope) -> Type | None:
        callee = expr.callee
        if not isinstance(callee, ast.Name):
            raise TypeCheckError("only named functions can be called in v0.0",
                                 expr.line, expr.column)
        name = callee.ident
        if name == "print":
            if len(expr.args) != 1:
                raise TypeCheckError("print() takes exactly one argument",
                                     expr.line, expr.column)
            at = self._expect_value(expr.args[0], scope, None)
            if not isinstance(at, (IntType, BoolType, StrType)):
                raise TypeCheckError(
                    f"print() cannot print a value of type '{type_name(at)}'",
                    expr.line, expr.column,
                )
            expr.resolved_type = None
            return None
        sig = self.functions.get(name)
        if sig is None:
            raise TypeCheckError(f"unknown function '{name}'", expr.line, expr.column)
        if len(expr.args) != len(sig.params):
            raise TypeCheckError(
                f"function '{name}' expects {len(sig.params)} argument(s), "
                f"got {len(expr.args)}",
                expr.line, expr.column,
            )
        for arg, ptype in zip(expr.args, sig.params):
            at = self._expect_value(arg, scope, ptype)
            if at != ptype:
                raise TypeCheckError(
                    f"argument type mismatch in call to '{name}': expected "
                    f"'{type_name(ptype)}', found '{type_name(at)}'",
                    arg.line, arg.column,
                )
        expr.resolved_type = sig.ret
        return sig.ret

    def _infer_field(self, expr: ast.FieldAccess, scope: _Scope) -> Type:
        base = self._expect_value(expr.target, scope, None)
        if not isinstance(base, StructType):
            raise TypeCheckError(
                f"type '{type_name(base)}' has no fields", expr.line, expr.column
            )
        fields = self.structs[base.name]
        if expr.field_name not in fields:
            raise TypeCheckError(
                f"struct '{base.name}' has no field '{expr.field_name}'",
                expr.line, expr.column,
            )
        ft = fields[expr.field_name]
        expr.resolved_type = ft
        return ft

    def _infer_struct_lit(self, expr: ast.StructLit, scope: _Scope) -> Type:
        if expr.type_name not in self.structs:
            raise TypeCheckError(f"unknown struct '{expr.type_name}'", expr.line, expr.column)
        fields = self.structs[expr.type_name]
        provided: dict[str, ast.FieldInit] = {}
        for init in expr.fields:
            if init.name in provided:
                raise TypeCheckError(
                    f"duplicate field '{init.name}' in struct literal", init.line, init.column
                )
            if init.name not in fields:
                raise TypeCheckError(
                    f"struct '{expr.type_name}' has no field '{init.name}'",
                    init.line, init.column,
                )
            provided[init.name] = init
            vt = self._expect_value(init.value, scope, fields[init.name])
            if vt != fields[init.name]:
                raise TypeCheckError(
                    f"field '{init.name}': expected '{type_name(fields[init.name])}', "
                    f"found '{type_name(vt)}'",
                    init.line, init.column,
                )
        missing = [n for n in fields if n not in provided]
        if missing:
            raise TypeCheckError(
                f"missing field(s) in '{expr.type_name}' literal: {', '.join(missing)}",
                expr.line, expr.column,
            )
        st = StructType(expr.type_name)
        expr.resolved_type = st
        return st


def _block_returns(block: ast.Block) -> bool:
    """Whether `block` is guaranteed to return on every path.

    Conservative: loops are assumed possibly-skipped, so only `return` and
    fully-covered `if`/`else` chains count. Statements after a definite return
    are unreachable but harmless here.
    """
    return any(_stmt_returns(s) for s in block.statements)


def _stmt_returns(stmt: ast.Stmt) -> bool:
    if isinstance(stmt, ast.Return):
        return True
    if isinstance(stmt, ast.If):
        if not _block_returns(stmt.then):
            return False
        if isinstance(stmt.otherwise, ast.If):
            return _stmt_returns(stmt.otherwise)
        if isinstance(stmt.otherwise, ast.Block):
            return _block_returns(stmt.otherwise)
        return False  # no else branch
    return False


def _is_flexible_int_lit(node: ast.Expr) -> bool:
    """An unsuffixed integer literal can still adopt another integer type."""
    return isinstance(node, ast.IntLit) and node.suffix is None


def check(program: ast.Program) -> Checker:
    """Type-check `program`, returning the populated Checker (raises on error)."""
    return Checker(program).check()
