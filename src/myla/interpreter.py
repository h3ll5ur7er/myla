"""The Myla tree-walking interpreter (docs/architecture.md §6).

Runs a type-checked `Program`: it relies on the `resolved_type` annotations the
checker attaches to expressions (for integer wrapping and for formatting values
in `print`). Integer arithmetic wraps at each type's width; structs have value
semantics (copied on binding, assignment, argument passing, return, and struct
construction).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ast
from .errors import MylaRuntimeError
from .types import (
    BoolType, CharType, Checker, FloatType, IntType, StrType, Type,
    char_utf8_bytes, float_div, float_rem, format_float, round_float,
)

# Overloadable binary operators → the operator-trait method dispatched on a
# user value (v0.4.4). `==`/`!=` use `eq`; the comparisons use `cmp`.
_OP_METHODS = {
    "+": "add", "-": "sub", "*": "mul", "/": "div", "%": "rem",
    "==": "eq", "!=": "eq", "<": "cmp", "<=": "cmp", ">": "cmp", ">=": "cmp",
}


class _ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class _BreakSignal(Exception):
    """Raised by `break`; caught by the innermost enclosing loop."""


class _ContinueSignal(Exception):
    """Raised by `continue`; caught by the innermost enclosing loop."""


class _ExitSignal(Exception):
    """Raised by `std.process.exit` (`__exit`); caught at the program entry to
    yield the process exit status (the low 8 bits, matching the native backend's
    `exit` syscall)."""

    def __init__(self, code: int):
        self.code = code & 0xFF


class StructValue:
    """A runtime struct instance with value semantics."""

    __slots__ = ("name", "fields")

    def __init__(self, name: str, fields: dict):
        self.name = name
        self.fields = fields

    def copy(self) -> "StructValue":
        return StructValue(self.name, {k: _copy(v) for k, v in self.fields.items()})

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, StructValue)
            and self.name == other.name
            and self.fields == other.fields
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        inner = ", ".join(f"{k}: {v!r}" for k, v in self.fields.items())
        return f"{self.name} {{ {inner} }}"


class TupleValue:
    """A runtime tuple instance with value semantics."""

    __slots__ = ("elems",)

    def __init__(self, elems: list):
        self.elems = elems

    def copy(self) -> "TupleValue":
        return TupleValue([_copy(v) for v in self.elems])

    def __eq__(self, other) -> bool:
        return isinstance(other, TupleValue) and self.elems == other.elems

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "(" + ", ".join(repr(v) for v in self.elems) + ")"


class EnumValue:
    """A runtime enum instance: a variant tag plus its (copied) payload."""

    __slots__ = ("enum_name", "variant", "payload")

    def __init__(self, enum_name: str, variant: str, payload: list):
        self.enum_name = enum_name
        self.variant = variant
        self.payload = payload

    def copy(self) -> "EnumValue":
        return EnumValue(self.enum_name, self.variant, [_copy(v) for v in self.payload])

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, EnumValue)
            and self.enum_name == other.enum_name
            and self.variant == other.variant
            and self.payload == other.payload
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if not self.payload:
            return f"{self.enum_name}.{self.variant}"
        inner = ", ".join(repr(v) for v in self.payload)
        return f"{self.enum_name}.{self.variant}({inner})"


class ListValue:
    """A runtime list `[T]` with value semantics. Copy-on-write is an
    implementation detail of the native backend; the tree-walking interpreter
    just deep-copies on every binding/assignment/pass (via `_copy`), which gives
    the same observable deep immutability (D14/D38)."""

    __slots__ = ("elems",)

    def __init__(self, elems: list):
        self.elems = elems

    def copy(self) -> "ListValue":
        return ListValue([_copy(v) for v in self.elems])

    def __eq__(self, other) -> bool:
        return isinstance(other, ListValue) and self.elems == other.elems

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "[" + ", ".join(repr(v) for v in self.elems) + "]"


class MapValue:
    """A runtime map `[K: V]` with value semantics. Like `ListValue`, the
    interpreter deep-copies on every binding/assignment/pass (via `_copy`),
    matching the native backend's copy-on-write observable behaviour (D38).
    Iteration order is insertion order (the language leaves it unspecified)."""

    __slots__ = ("entries",)

    def __init__(self, entries: dict | None = None):
        self.entries: dict = entries if entries is not None else {}

    def copy(self) -> "MapValue":
        return MapValue({k: _copy(v) for k, v in self.entries.items()})

    def __eq__(self, other) -> bool:
        return isinstance(other, MapValue) and self.entries == other.entries

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "[" + ", ".join(f"{k!r}: {v!r}" for k, v in self.entries.items()) + "]"


class StringBuilderValue:
    """A runtime `StringBuilder` (D41): a growable byte buffer with value
    semantics. The interpreter deep-copies on bind/assign/pass (via `_copy`),
    matching the native backend's copy-on-write behaviour."""

    __slots__ = ("buf",)

    def __init__(self, buf: bytearray | None = None):
        self.buf: bytearray = buf if buf is not None else bytearray()

    def copy(self) -> "StringBuilderValue":
        return StringBuilderValue(bytearray(self.buf))

    def __eq__(self, other) -> bool:
        return isinstance(other, StringBuilderValue) and self.buf == other.buf

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"StringBuilder({bytes(self.buf)!r})"


class ClosureValue:
    """A runtime function value (v0.4.2): a callable body plus a snapshot of its
    captured environment.

    Mirrors the native `(code_ptr, env_ptr)` fat value. `params` are the lambda
    (or referenced `fun`) parameters, `body` is an expression or a `Block`, and
    `env` maps each captured name to its by-value snapshot taken at creation
    (D15). A plain `fun` reference has an empty `env`."""

    __slots__ = ("params", "body", "env", "is_block")

    def __init__(self, params, body, env: dict, is_block: bool):
        self.params = params
        self.body = body
        self.env = env
        self.is_block = is_block

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<closure {len(self.params)} param(s), {len(self.env)} capture(s)>"


def _copy(value):
    if isinstance(value, (StructValue, TupleValue, EnumValue, ListValue, MapValue,
                          StringBuilderValue)):
        return value.copy()
    return value


class _Env:
    def __init__(self, parent: "_Env | None" = None):
        self.parent = parent
        self.vars: dict[str, object] = {}

    def define(self, name: str, value) -> None:
        self.vars[name] = value

    def get(self, name: str):
        env: _Env | None = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise KeyError(name)  # pragma: no cover - checker prevents this

    def assign(self, name: str, value) -> None:
        env: _Env | None = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return
            env = env.parent
        raise KeyError(name)  # pragma: no cover


@dataclass
class TestResult:
    function: str
    index: int
    passed: bool
    detail: str


class Interpreter:
    def __init__(self, checker: Checker, out=None, err=None, argv=None):
        self.checker = checker
        self.functions = checker.functions  # name -> FuncSig
        self._consts = {name: info.value for name, info in checker.consts.items()}
        import sys
        self._out = out if out is not None else sys.stdout
        self._err = err if err is not None else sys.stderr
        # process command-line arguments handed back by `std.process.args`.
        self._argv = list(argv) if argv is not None else []
        # errno of the last `__read_file` (0 on success); read by `__io_errno`.
        self._io_errno = 0
        # captured result of the last `__run` (see `std.process.run`): stderr
        # bytes, the normal exit code, the terminating signal (0 if none), and
        # the spawn errno (0 on success). Read by the `__run_*` primitives.
        self._run_stderr: list[int] = []
        self._run_exit_code = 0
        self._run_signal = 0
        self._run_errno = 0

    # -- program entry -------------------------------------------------------

    def run(self) -> int:
        """Execute the program, returning its exit status (0 on normal
        completion, or the code passed to `std.process.exit`)."""
        if self.checker.entry is None:
            raise MylaRuntimeError("no entry point: define '#main' or a function named 'main'")
        try:
            self._call(self.checker.entry, [])
        except _ExitSignal as sig:
            return sig.code
        return 0

    def run_tests(self) -> list[TestResult]:
        results: list[TestResult] = []
        for decl in self.checker.program.decls:
            if not isinstance(decl, ast.FunDecl):
                continue
            idx = 0
            for attr in decl.attributes:
                if attr.name != "test":
                    continue
                idx += 1
                args = [self._eval(a, _Env()) for a in attr.args]
                expected = self._eval(attr.outputs[0], _Env())
                try:
                    actual = self._call(decl, args)
                except MylaRuntimeError as err:
                    results.append(TestResult(decl.name, idx, False, f"runtime error: {err.message}"))
                    continue
                if actual == expected:
                    results.append(TestResult(decl.name, idx, True, ""))
                else:
                    results.append(TestResult(
                        decl.name, idx, False,
                        f"expected {expected!r}, got {actual!r}",
                    ))
        return results

    # -- calls & statements --------------------------------------------------

    def _call(self, decl: ast.FunDecl, args: list):
        frame = _Env()
        for param, value in zip(decl.params, args):
            frame.define(param.name, _copy(value))
        try:
            self._exec_block(decl.body, frame)
        except _ReturnSignal as ret:
            return ret.value
        return None

    def _exec_block(self, block: ast.Block, parent: _Env) -> None:
        env = _Env(parent)
        for stmt in block.statements:
            self._exec_stmt(stmt, env)

    def _exec_stmt(self, stmt: ast.Stmt, env: _Env) -> None:
        if isinstance(stmt, ast.VarDecl):
            env.define(stmt.name, _copy(self._eval(stmt.init, env)))

        elif isinstance(stmt, ast.DestructDecl):
            value = self._eval(stmt.init, env)
            self._bind_pattern(stmt.binding, value, env)

        elif isinstance(stmt, ast.Assign):
            value = _copy(self._eval(stmt.value, env))
            target = stmt.target
            if isinstance(target, ast.Name):
                env.assign(target.ident, value)
            elif isinstance(target, ast.Index):
                container = self._eval(target.target, env)
                key = self._eval(target.index, env)
                if isinstance(container, MapValue):
                    container.entries[key] = value
                elif key < 0 or key >= len(container.elems):
                    raise MylaRuntimeError(
                        f"list index {key} out of bounds (len {len(container.elems)})",
                        target.line, target.column,
                    )
                else:
                    container.elems[key] = value
            else:  # FieldAccess chain
                assert isinstance(target, ast.FieldAccess)
                container = self._resolve_struct(target.target, env)
                container.fields[target.field_name] = value

        elif isinstance(stmt, ast.If):
            if self._eval(stmt.cond, env):
                self._exec_block(stmt.then, env)
            elif isinstance(stmt.otherwise, ast.If):
                self._exec_stmt(stmt.otherwise, env)
            elif isinstance(stmt.otherwise, ast.Block):
                self._exec_block(stmt.otherwise, env)

        elif isinstance(stmt, ast.While):
            while self._eval(stmt.cond, env):
                try:
                    self._exec_block(stmt.body, env)
                except _ContinueSignal:
                    continue
                except _BreakSignal:
                    break

        elif isinstance(stmt, ast.For):
            if stmt.iterable is not None:  # `for v in xs/m` — list/map iteration
                target = self._eval(stmt.iterable, env)
                if isinstance(target, MapValue):
                    items = list(target.entries.keys())  # keys snapshot
                else:
                    items = list(target.elems)  # snapshot: body can't mutate it
            else:  # `for v in start..end`
                items = range(self._eval(stmt.start, env), self._eval(stmt.end, env))
            for item in items:
                body_env = _Env(env)
                body_env.define(stmt.var_name, _copy(item))
                try:
                    for s in stmt.body.statements:
                        self._exec_stmt(s, body_env)
                except _ContinueSignal:
                    continue
                except _BreakSignal:
                    break

        elif isinstance(stmt, ast.Break):
            raise _BreakSignal()

        elif isinstance(stmt, ast.Continue):
            raise _ContinueSignal()

        elif isinstance(stmt, ast.Return):
            value = self._eval(stmt.value, env) if stmt.value is not None else None
            raise _ReturnSignal(value)

        elif isinstance(stmt, ast.ExprStmt):
            self._eval(stmt.expr, env)

        else:  # pragma: no cover - defensive
            raise MylaRuntimeError(f"cannot execute {type(stmt).__name__}", stmt.line, stmt.column)

    def _eval_match(self, expr: ast.Match, env: _Env):
        scrut = self._eval(expr.scrutinee, env)
        for arm in expr.arms:
            binds: dict[str, object] = {}
            if not self._match_pattern(arm.pattern, scrut, binds):
                continue
            arm_env = _Env(env)
            for name, val in binds.items():
                arm_env.define(name, val)
            if arm.guard is not None and not self._eval(arm.guard, arm_env):
                continue
            return self._eval_arm_body(arm.body, arm_env)
        raise MylaRuntimeError(  # pragma: no cover - checker enforces exhaustiveness
            "no match arm matched", expr.line, expr.column
        )

    def _eval_arm_body(self, body, env: _Env):
        if isinstance(body, ast.Block):
            inner = _Env(env)
            stmts = body.statements
            for i, s in enumerate(stmts):
                if i == len(stmts) - 1 and isinstance(s, ast.ExprStmt):
                    return self._eval(s.expr, inner)
                self._exec_stmt(s, inner)
            return None
        return self._eval(body, env)

    def _match_pattern(self, pat, value, binds: dict) -> bool:
        if isinstance(pat, ast.PatWildcard):
            return True
        if isinstance(pat, ast.PatBinding):
            variant = getattr(pat, "as_variant", None)
            if variant is not None:
                return isinstance(value, EnumValue) and value.variant == variant[1]
            binds[pat.name] = _copy(value)
            return True
        if isinstance(pat, ast.PatLiteral):
            return self._eval(pat.literal, _Env()) == value
        if isinstance(pat, ast.PatEnum):
            if not isinstance(value, EnumValue) or value.variant != pat.variant:
                return False
            for sub, item in zip(pat.elems, value.payload):
                if not self._match_pattern(sub, item, binds):
                    return False
            return True
        if isinstance(pat, ast.PatTuple):
            assert isinstance(value, TupleValue)
            for sub, item in zip(pat.elems, value.elems):
                if not self._match_pattern(sub, item, binds):
                    return False
            return True
        if isinstance(pat, ast.PatStruct):
            assert isinstance(value, StructValue)
            for fp in pat.fields:
                if not self._match_pattern(fp.pattern, value.fields[fp.name], binds):
                    return False
            return True
        if isinstance(pat, ast.PatOr):
            for alt in pat.alts:
                trial: dict[str, object] = {}
                if self._match_pattern(alt, value, trial):
                    binds.update(trial)
                    return True
            return False
        raise MylaRuntimeError(  # pragma: no cover - defensive
            "unsupported pattern", pat.line, pat.column
        )

    def _bind_pattern(self, binding, value, env: _Env) -> None:
        if isinstance(binding, ast.BindWildcard):
            return
        if isinstance(binding, ast.BindName):
            env.define(binding.name, _copy(value))
            return
        assert isinstance(binding, ast.BindTuple)
        assert isinstance(value, TupleValue)
        for elem, v in zip(binding.elems, value.elems):
            self._bind_pattern(elem, v, env)

    def _resolve_struct(self, expr: ast.Expr, env: _Env) -> StructValue:
        """Return the actual (non-copied) StructValue an lvalue chain refers to."""
        if isinstance(expr, ast.Name):
            return env.get(expr.ident)
        if isinstance(expr, ast.FieldAccess):
            parent = self._resolve_struct(expr.target, env)
            return parent.fields[expr.field_name]
        if isinstance(expr, ast.Index):
            container = self._eval(expr.target, env)
            key = self._eval(expr.index, env)
            if isinstance(container, MapValue):
                if key not in container.entries:
                    raise MylaRuntimeError(f"map key {key!r} not found",
                                           expr.line, expr.column)
                return container.entries[key]
            if key < 0 or key >= len(container.elems):
                raise MylaRuntimeError(
                    f"list index {key} out of bounds (len {len(container.elems)})",
                    expr.line, expr.column,
                )
            return container.elems[key]
        raise MylaRuntimeError("invalid assignment target", expr.line, expr.column)  # pragma: no cover

    # -- expression evaluation ----------------------------------------------

    def _eval(self, expr: ast.Expr, env: _Env):
        if isinstance(expr, ast.IntLit):
            return _wrap(expr.value, expr.resolved_type)
        if isinstance(expr, ast.FloatLit):
            return round_float(expr.value, expr.resolved_type)
        if isinstance(expr, ast.BoolLit):
            return expr.value
        if isinstance(expr, ast.StrLit):
            return expr.value
        if isinstance(expr, ast.Name):
            ctor = getattr(expr, "enum_ctor", None)
            if ctor is not None:  # bare no-payload prelude variant, e.g. `None`
                return EnumValue(ctor[0], ctor[1], [])
            ref = getattr(expr, "const_ref", None)
            if ref is not None:  # module-level const
                return self._consts[ref]
            fref = getattr(expr, "func_ref", None)
            if fref is not None:  # a top-level `fun` used as a value (v0.4.2)
                decl = self.functions[fref].decl
                return ClosureValue(decl.params, decl.body, {}, True)
            return env.get(expr.ident)
        if isinstance(expr, ast.Unary):
            return self._eval_unary(expr, env)
        if isinstance(expr, ast.Binary):
            return self._eval_binary(expr, env)
        if isinstance(expr, ast.Call):
            return self._eval_call(expr, env)
        if isinstance(expr, ast.FieldAccess):
            ctor = getattr(expr, "enum_ctor", None)
            if ctor is not None:  # no-payload variant, e.g. `Color.Red`
                return EnumValue(ctor[0], ctor[1], [])
            container = self._eval(expr.target, env)
            return container.fields[expr.field_name]
        if isinstance(expr, ast.StructLit):
            fields = {fi.name: _copy(self._eval(fi.value, env)) for fi in expr.fields}
            return StructValue(expr.type_name, fields)
        if isinstance(expr, ast.TupleLit):
            return TupleValue([_copy(self._eval(e, env)) for e in expr.elems])
        if isinstance(expr, ast.TupleIndex):
            container = self._eval(expr.target, env)
            return container.elems[expr.index]
        if isinstance(expr, ast.ListLit):
            return ListValue([_copy(self._eval(e, env)) for e in expr.elems])
        if isinstance(expr, ast.MapLit):
            m = MapValue()
            for k, v in expr.entries:
                m.entries[self._eval(k, env)] = _copy(self._eval(v, env))
            return m
        if isinstance(expr, ast.Index):
            return self._index_read(expr, env)
        if isinstance(expr, ast.Match):
            return self._eval_match(expr, env)
        if isinstance(expr, ast.Cast):
            return _cast_value(self._eval(expr.operand, env),
                               expr.operand.resolved_type, expr.resolved_type)
        if isinstance(expr, ast.Lambda):
            captured = {name: _copy(env.get(name)) for name, _t in expr.captures}
            return ClosureValue(expr.params, expr.body, captured,
                                isinstance(expr.body, ast.Block))
        raise MylaRuntimeError(  # pragma: no cover
            f"cannot evaluate {type(expr).__name__}", expr.line, expr.column
        )

    def _call_closure(self, clo: "ClosureValue", args: list):
        frame = _Env()
        for name, value in clo.env.items():
            frame.define(name, value)
        for param, value in zip(clo.params, args):
            frame.define(param.name, _copy(value))
        if not clo.is_block:
            return self._eval(clo.body, frame)
        try:
            self._exec_block(clo.body, frame)
        except _ReturnSignal as ret:
            return ret.value
        return None

    def _index_read(self, expr: ast.Index, env: _Env):
        target = self._eval(expr.target, env)
        key = self._eval(expr.index, env)
        if isinstance(target, str):
            data = target.encode("utf-8")
            if key < 0 or key >= len(data):
                raise MylaRuntimeError(
                    f"string index {key} out of bounds (len {len(data)})",
                    expr.line, expr.column,
                )
            return data[key]            # the byte value (uint8)
        if isinstance(target, MapValue):
            if key not in target.entries:
                raise MylaRuntimeError(
                    f"map key {key!r} not found", expr.line, expr.column,
                )
            return target.entries[key]
        if key < 0 or key >= len(target.elems):
            raise MylaRuntimeError(
                f"list index {key} out of bounds (len {len(target.elems)})",
                expr.line, expr.column,
            )
        return target.elems[key]

    def _eval_unary(self, expr: ast.Unary, env: _Env):
        v = self._eval(expr.operand, env)
        if expr.op == "-":
            return _wrap(-v, expr.resolved_type)
        if expr.op == "~":
            return _wrap(~v, expr.resolved_type)
        return not v  # "!"

    def _eval_binary(self, expr: ast.Binary, env: _Env):
        op = expr.op
        if op == "&&":
            return bool(self._eval(expr.left, env) and self._eval(expr.right, env))
        if op == "||":
            return bool(self._eval(expr.left, env) or self._eval(expr.right, env))

        left = self._eval(expr.left, env)
        right = self._eval(expr.right, env)

        # Operator overloading on user values (v0.4.4). Non-generic uses were
        # desugared to method calls at check time, so a struct/enum operand here
        # only arises inside a bounded generic body (erased `T`, X9): dispatch
        # at runtime to the operand type's operator-trait method.
        if op in _OP_METHODS and isinstance(left, (StructValue, EnumValue)):
            return self._dispatch_operator(op, left, right, expr)

        if op == "+":
            if isinstance(expr.resolved_type, StrType):
                return left + right          # string concatenation (D41)
            return _wrap(left + right, expr.resolved_type)
        if op == "-":
            return _wrap(left - right, expr.resolved_type)
        if op == "*":
            return _wrap(left * right, expr.resolved_type)
        if op == "/":
            if isinstance(expr.resolved_type, FloatType):
                # IEEE-754 true division: by zero yields ±inf/NaN, never traps.
                return _wrap(float_div(left, right), expr.resolved_type)
            if right == 0:
                raise MylaRuntimeError("division by zero", expr.line, expr.column)
            return _wrap(_idiv(left, right), expr.resolved_type)
        if op == "%":
            if isinstance(expr.resolved_type, FloatType):
                return _wrap(float_rem(left, right), expr.resolved_type)
            if right == 0:
                raise MylaRuntimeError("modulo by zero", expr.line, expr.column)
            return _wrap(_imod(left, right), expr.resolved_type)
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "&":
            return _wrap(left & right, expr.resolved_type)
        if op == "|":
            return _wrap(left | right, expr.resolved_type)
        if op == "^":
            return _wrap(left ^ right, expr.resolved_type)
        if op == "<<":
            return _wrap(left << (right & (expr.resolved_type.width - 1)), expr.resolved_type)
        if op == ">>":
            return self._eval_shr(left, right, expr.resolved_type)
        raise MylaRuntimeError(f"unknown operator '{op}'", expr.line, expr.column)  # pragma: no cover

    def _dispatch_operator(self, op: str, left, right, expr: ast.Binary):
        key = left.name if isinstance(left, StructValue) else left.enum_name
        if op in ("==", "!="):
            same = self._call_op_method(key, "eq", left, right, expr)
            return same if op == "==" else not same
        if op in ("<", "<=", ">", ">="):
            c = self._call_op_method(key, "cmp", left, right, expr)
            if op == "<":
                return c < 0
            if op == "<=":
                return c <= 0
            if op == ">":
                return c > 0
            return c >= 0
        return self._call_op_method(key, _OP_METHODS[op], left, right, expr)

    def _call_op_method(self, key: str, method: str, left, right,
                        expr: ast.Binary):
        sig = self.functions.get(f"{key}.{method}")
        if sig is None:  # pragma: no cover - guaranteed by the checker/bounds
            raise MylaRuntimeError(
                f"type '{key}' has no '{method}' method for operator dispatch",
                expr.line, expr.column,
            )
        frame = _Env()
        frame.define("self", _copy(left))
        frame.define(sig.decl.params[1].name, _copy(right))
        try:
            self._exec_block(sig.decl.body, frame)
        except _ReturnSignal as ret:
            return ret.value
        return None

    @staticmethod
    def _eval_shr(left: int, right: int, t: Type) -> int:
        # Mask the shift count to the operand width (matching the hardware shift
        # instructions the compiler emits) and shift on the wrapped value so the
        # result is arithmetic for signed types and logical for unsigned ones.
        count = right & (t.width - 1)
        return _wrap(_wrap(left, t) >> count, t)

    def _run_process(self, program: str, argv: list[str]) -> "ListValue":
        """Spawn `program` with `argv`, wait for it, and capture its output.

        Mirrors the native `__run` primitive: the program is located by the
        exact path given (no PATH search) and inherits the current environment.
        stdout is returned as a `[uint8]` list; stderr, the exit code, the
        terminating signal, and the spawn errno are stashed for the `__run_*`
        primitives.
        """
        import subprocess
        try:
            proc = subprocess.run(argv, executable=program, capture_output=True)
        except OSError as err:
            self._run_errno = err.errno or 2
            self._run_stderr = []
            self._run_exit_code = -1
            self._run_signal = 0
            return ListValue([])
        self._run_errno = 0
        self._run_stderr = list(proc.stderr)
        rc = proc.returncode
        if rc < 0:  # killed by signal `-rc`
            self._run_signal = -rc
            self._run_exit_code = -1
        else:
            self._run_signal = 0
            self._run_exit_code = rc
        return ListValue(list(proc.stdout))

    def _eval_call(self, expr: ast.Call, env: _Env):
        ctor = getattr(expr, "enum_ctor", None)
        if ctor is not None:  # `Enum.Variant(args...)`
            payload = [_copy(self._eval(a, env)) for a in expr.args]
            return EnumValue(ctor[0], ctor[1], payload)
        mfunc = getattr(expr, "method_func", None)
        if mfunc is not None:  # `recv.method(args)` (v0.4.1)
            return self._eval_method_call(expr, env, mfunc)
        if getattr(expr, "indirect_call", False):  # `f(args)` value call (v0.4.2)
            clo = self._eval(expr.callee, env)
            args = [self._eval(a, env) for a in expr.args]
            return self._call_closure(clo, args)
        callee = expr.callee
        assert isinstance(callee, ast.Name)
        if callee.ident == "print":
            arg = expr.args[0]
            value = self._eval(arg, env)
            self._out.write(_format_value(value, arg.resolved_type) + "\n")
            return None
        if callee.ident in ("assert", "panic", "unreachable"):
            return self._eval_intrinsic(expr, env)
        if callee.ident == "__write":
            fd = self._eval(expr.args[0], env)
            s = self._eval(expr.args[1], env)
            if fd == 1:
                self._out.write(s)
            elif fd == 2:
                self._err.write(s)
            else:
                import os
                os.write(fd, s.encode("utf-8"))
            return None
        if callee.ident == "__exit":
            raise _ExitSignal(self._eval(expr.args[0], env))
        if callee.ident == "__args":
            return ListValue(list(self._argv))
        if callee.ident == "__read_file":
            path = self._eval(expr.args[0], env)
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
                self._io_errno = 0
                # decode like the native backend treats the bytes as UTF-8; the
                # byte length (what `len` reports) is preserved for valid UTF-8.
                return data.decode("utf-8", errors="surrogateescape")
            except OSError as err:
                self._io_errno = err.errno or 0
                return ""
        if callee.ident == "__io_errno":
            return self._io_errno
        if callee.ident == "__run":
            program = self._eval(expr.args[0], env)
            argv = [str(a) for a in self._eval(expr.args[1], env).elems]
            return self._run_process(program, argv)
        if callee.ident == "__run_stderr":
            return ListValue(list(self._run_stderr))
        if callee.ident == "__run_exit_code":
            return self._run_exit_code
        if callee.ident == "__run_signal":
            return self._run_signal
        if callee.ident == "__run_errno":
            return self._run_errno
        if callee.ident == "len":
            target = self._eval(expr.args[0], env)
            if isinstance(target, str):
                return len(target.encode("utf-8"))
            if isinstance(target, MapValue):
                return len(target.entries)
            if isinstance(target, StringBuilderValue):
                return len(target.buf)
            return len(target.elems)
        if callee.ident == "push":
            lst = self._eval(expr.args[0], env)
            lst.elems.append(_copy(self._eval(expr.args[1], env)))
            return None
        if callee.ident == "pop":
            lst = self._eval(expr.args[0], env)
            if not lst.elems:
                raise MylaRuntimeError("pop from an empty list",
                                       expr.line, expr.column)
            return lst.elems.pop()
        if callee.ident == "chars":
            s = self._eval(expr.args[0], env)
            return ListValue([ord(c) for c in s])   # one codepoint per scalar

        if callee.ident == "contains":
            m = self._eval(expr.args[0], env)
            return self._eval(expr.args[1], env) in m.entries
        if callee.ident == "remove":
            m = self._eval(expr.args[0], env)
            m.entries.pop(self._eval(expr.args[1], env), None)
            return None
        if callee.ident == "format":
            fmt = expr.args[0].value          # checked to be a string literal
            parts = [_format_value(self._eval(a, env), a.resolved_type)
                     for a in expr.args[1:]]
            return _render_format(fmt, parts)
        if callee.ident == "StringBuilder":
            return StringBuilderValue()
        if callee.ident == "append":
            sb = self._eval(expr.args[0], env)
            sb.buf.extend(self._eval(expr.args[1], env).encode("utf-8"))
            return None
        if callee.ident == "append_byte":
            sb = self._eval(expr.args[0], env)
            sb.buf.append(self._eval(expr.args[1], env) & 0xFF)
            return None
        if callee.ident == "build":
            sb = self._eval(expr.args[0], env)
            return bytes(sb.buf).decode("utf-8", errors="surrogateescape")
        if callee.ident == "keys":
            m = self._eval(expr.args[0], env)
            return ListValue([_copy(k) for k in m.entries.keys()])
        sig = self.functions[callee.ident]
        args = [self._eval(a, env) for a in expr.args]
        return self._call(sig.decl, args)

    def _eval_method_call(self, expr: ast.Call, env: _Env, mfunc: str):
        decl = self.functions[mfunc].decl
        recv_expr = expr.callee.target
        is_var_self = getattr(expr, "method_is_var_self", False)
        # For `var self`, bind `self` to the *actual* receiver object (no copy)
        # so in-place field/element mutations write back to the caller. For a
        # read-only `self`, bind a copy (value semantics).
        if is_var_self:
            recv = self._resolve_struct(recv_expr, env)
        else:
            recv = _copy(self._eval(recv_expr, env))
        args = [_copy(self._eval(a, env)) for a in expr.args]
        frame = _Env()
        frame.define("self", recv)
        for param, value in zip(decl.params[1:], args):
            frame.define(param.name, value)
        try:
            self._exec_block(decl.body, frame)
        except _ReturnSignal as ret:
            return ret.value
        return None

    def _eval_intrinsic(self, expr: ast.Call, env: _Env):
        name = expr.callee.ident
        if name == "assert":
            if not self._eval(expr.args[0], env):
                msg = (self._eval(expr.args[1], env) if len(expr.args) == 2
                       else "assertion failed")
                raise MylaRuntimeError(msg, expr.line, expr.column)
            return None
        if name == "panic":
            raise MylaRuntimeError(self._eval(expr.args[0], env),
                                   expr.line, expr.column)
        # unreachable
        raise MylaRuntimeError("reached unreachable code", expr.line, expr.column)


# --- helpers ---------------------------------------------------------------


def _wrap(value, t: Type):
    # In an erased generic body a numeric operator's result type can be a bare
    # type parameter (v0.4.4 `T: Add`); the interpreter has no concrete width to
    # wrap to, so it keeps the exact Python value (the native backend wraps the
    # monomorphized concrete type). Every other caller passes an `IntType`/`FloatType`.
    if isinstance(t, FloatType):
        return round_float(value, t)   # narrow to single precision for `float32`
    if isinstance(t, CharType):
        return value                   # a char is its raw codepoint (no wrapping)
    if not isinstance(t, IntType):
        return value
    mask = (1 << t.width) - 1
    m = value & mask
    if t.signed and (m >> (t.width - 1)) & 1:
        m -= 1 << t.width
    return m


def _cast_value(v, src: Type, target: Type):
    """Apply an `as` numeric conversion at runtime (mirrors the native backend
    and const folding): int↔int wrap, int→float round, float→int truncate
    toward zero, float→float widen/round."""
    if isinstance(target, CharType):
        return int(v)                  # int -> char: the codepoint (unchecked)
    if isinstance(src, CharType):
        return _wrap(int(v), target)   # char -> int: wrap to width
    if isinstance(target, FloatType):
        return round_float(float(v), target)
    if isinstance(src, FloatType):
        return _wrap(int(v), target)   # float -> int: truncate toward zero
    return _wrap(v, target)


def _idiv(a: int, b: int) -> int:
    """Integer division truncated toward zero (C/Rust semantics)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _imod(a: int, b: int) -> int:
    return a - _idiv(a, b) * b


def _format_value(value, t: Type | None) -> str:
    if isinstance(t, BoolType):
        return "true" if value else "false"
    if isinstance(t, StrType):
        return value
    if isinstance(t, IntType):
        return str(value)
    if isinstance(t, FloatType):
        return format_float(value, t)
    if isinstance(t, CharType):
        return char_utf8_bytes(value).decode("utf-8")   # render as its glyph
    return str(value)  # pragma: no cover - print() is restricted by the checker


def _render_format(fmt: str, parts: list[str]) -> str:
    """Substitute already-rendered `parts` into `{}` placeholders of `fmt`
    (`{{`/`}}` are literal braces). The checker guarantees the counts match."""
    out: list[str] = []
    i = 0
    n = len(fmt)
    arg = 0
    while i < n:
        c = fmt[i]
        if c == "{" and i + 1 < n and fmt[i + 1] == "{":
            out.append("{")
            i += 2
        elif c == "}" and i + 1 < n and fmt[i + 1] == "}":
            out.append("}")
            i += 2
        elif c == "{" and i + 1 < n and fmt[i + 1] == "}":
            out.append(parts[arg])
            arg += 1
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def run(checker: Checker, out=None) -> None:
    Interpreter(checker, out).run()
