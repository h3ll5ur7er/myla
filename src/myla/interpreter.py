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


def _copy(value):
    return value.copy() if isinstance(value, StructValue) else value


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
            return env.get(expr.ident)
        if isinstance(expr, ast.Unary):
            return self._eval_unary(expr, env)
        if isinstance(expr, ast.Binary):
            return self._eval_binary(expr, env)
        if isinstance(expr, ast.Call):
            return self._eval_call(expr, env)
        if isinstance(expr, ast.FieldAccess):
            container = self._eval(expr.target, env)
            return container.fields[expr.field_name]
        if isinstance(expr, ast.StructLit):
            fields = {fi.name: _copy(self._eval(fi.value, env)) for fi in expr.fields}
            return StructValue(expr.type_name, fields)
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
