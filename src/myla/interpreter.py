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
from .types import BoolType, Checker, IntType, StrType, Type


class _ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


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


def _copy(value):
    if isinstance(value, (StructValue, TupleValue, EnumValue)):
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
    def __init__(self, checker: Checker, out=None):
        self.checker = checker
        self.functions = checker.functions  # name -> FuncSig
        import sys
        self._out = out if out is not None else sys.stdout

    # -- program entry -------------------------------------------------------

    def run(self) -> None:
        if self.checker.entry is None:
            raise MylaRuntimeError("no entry point: define '#main' or a function named 'main'")
        self._call(self.checker.entry, [])

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
                self._exec_block(stmt.body, env)

        elif isinstance(stmt, ast.For):
            start = self._eval(stmt.start, env)
            end = self._eval(stmt.end, env)
            for i in range(start, end):
                body_env = _Env(env)
                body_env.define(stmt.var_name, i)
                for s in stmt.body.statements:
                    self._exec_stmt(s, body_env)

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
        raise MylaRuntimeError("invalid assignment target", expr.line, expr.column)  # pragma: no cover

    # -- expression evaluation ----------------------------------------------

    def _eval(self, expr: ast.Expr, env: _Env):
        if isinstance(expr, ast.IntLit):
            return _wrap(expr.value, expr.resolved_type)
        if isinstance(expr, ast.BoolLit):
            return expr.value
        if isinstance(expr, ast.StrLit):
            return expr.value
        if isinstance(expr, ast.Name):
            ctor = getattr(expr, "enum_ctor", None)
            if ctor is not None:  # bare no-payload prelude variant, e.g. `None`
                return EnumValue(ctor[0], ctor[1], [])
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
        if isinstance(expr, ast.Match):
            return self._eval_match(expr, env)
        raise MylaRuntimeError(  # pragma: no cover
            f"cannot evaluate {type(expr).__name__}", expr.line, expr.column
        )

    def _eval_unary(self, expr: ast.Unary, env: _Env):
        v = self._eval(expr.operand, env)
        if expr.op == "-":
            return _wrap(-v, expr.resolved_type)
        return not v  # "!"

    def _eval_binary(self, expr: ast.Binary, env: _Env):
        op = expr.op
        if op == "&&":
            return bool(self._eval(expr.left, env) and self._eval(expr.right, env))
        if op == "||":
            return bool(self._eval(expr.left, env) or self._eval(expr.right, env))

        left = self._eval(expr.left, env)
        right = self._eval(expr.right, env)

        if op == "+":
            return _wrap(left + right, expr.resolved_type)
        if op == "-":
            return _wrap(left - right, expr.resolved_type)
        if op == "*":
            return _wrap(left * right, expr.resolved_type)
        if op == "/":
            if right == 0:
                raise MylaRuntimeError("division by zero", expr.line, expr.column)
            return _wrap(_idiv(left, right), expr.resolved_type)
        if op == "%":
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
        raise MylaRuntimeError(f"unknown operator '{op}'", expr.line, expr.column)  # pragma: no cover

    def _eval_call(self, expr: ast.Call, env: _Env):
        ctor = getattr(expr, "enum_ctor", None)
        if ctor is not None:  # `Enum.Variant(args...)`
            payload = [_copy(self._eval(a, env)) for a in expr.args]
            return EnumValue(ctor[0], ctor[1], payload)
        callee = expr.callee
        assert isinstance(callee, ast.Name)
        if callee.ident == "print":
            arg = expr.args[0]
            value = self._eval(arg, env)
            self._out.write(_format_value(value, arg.resolved_type) + "\n")
            return None
        sig = self.functions[callee.ident]
        args = [self._eval(a, env) for a in expr.args]
        return self._call(sig.decl, args)


# --- helpers ---------------------------------------------------------------


def _wrap(value: int, t: Type) -> int:
    assert isinstance(t, IntType)
    mask = (1 << t.width) - 1
    m = value & mask
    if t.signed and (m >> (t.width - 1)) & 1:
        m -= 1 << t.width
    return m


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
    return str(value)  # pragma: no cover - print() is restricted by the checker


def run(checker: Checker, out=None) -> None:
    Interpreter(checker, out).run()
