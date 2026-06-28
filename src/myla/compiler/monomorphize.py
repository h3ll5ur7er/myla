"""Monomorphization (D13): specialize generics into concrete copies.

The native backend keeps codegen simple by never seeing a type parameter: each
reachable instantiation of a generic `fun`/`struct`/`enum` is stamped out as its
own concrete declaration with a mangled name, and every reference (call, type
annotation, struct literal, enum constructor, pattern) is rewritten to the right
stamp.

The pass runs on a *type-checked* program — it reads the type arguments the
checker inferred at each site (`Call.type_args`, `expr.resolved_type`) — and
produces a fresh, fully concrete `Program` which is then re-checked and handed to
codegen. The original program is left untouched, so the interpreter can keep
running generics by erasure (a single body serves every instantiation).

What gets rewritten / dropped in the output:
  * generic `struct`/`enum` templates and *all* `typealias` decls are dropped;
    every type reference to them is resolved to a concrete type instead;
  * non-generic `struct`/`enum` decls are kept, but their field/payload type
    annotations are re-emitted concretely (so e.g. a `List<int>` field becomes
    the stamped `List__int32`);
  * generic instantiations reached anywhere are stamped as concrete decls.
Only a few node attributes must be corrected for the re-check to resolve names
(type annotations, `StructLit.type_name`, the enum constructor's name, and
pattern `enum_name`/`type_name`); everything else (`resolved_type`, `enum_ctor`,
`as_variant`, …) is recomputed by the re-check.
"""
from __future__ import annotations

import copy
import dataclasses

from .. import ast
from ..types import (
    BoolType, Checker, EnumType, IntType, ListType, MapType, StrType,
    StringBuilderType, StructType, TupleType, Type, TypeParam, check, type_name,
)


class _Monomorphizer:
    def __init__(self, checker: Checker):
        self.checker = checker
        self.funcs = checker.functions
        # function instantiations
        self.fn_mono_name: dict[tuple, str] = {}
        self.emitted_fns: dict[str, ast.FunDecl] = {}
        self.fn_worklist: list[tuple[str, dict[str, Type], str]] = []
        # generic type instantiations
        self.type_mono_name: dict[tuple, str] = {}
        self.type_worklist: list[Type] = []
        self.stamped_types: list[ast.Decl] = []

    def run(self) -> Checker:
        out: list[ast.Decl] = []
        # 1) non-generic structs/enums: keep, but re-emit field/payload types
        #    concretely (an alias / generic-instantiation member is resolved).
        for d in self.checker.program.decls:
            if isinstance(d, ast.StructDecl) and not d.type_params:
                c = copy.deepcopy(d)
                for f in c.fields:
                    f.type = self._rewrite_typeexpr(f.type, {})
                out.append(c)
            elif isinstance(d, ast.EnumDecl) and not d.type_params:
                c = copy.deepcopy(d)
                for v in c.variants:
                    v.payload = [self._rewrite_typeexpr(p, {}) for p in v.payload]
                out.append(c)
            elif isinstance(d, ast.ConstDecl):
                # Constants are kept as-is (their types are concrete primitives);
                # the re-check re-folds the value. Initializers reference only
                # literals/other consts, so no type rewriting is needed.
                c = copy.deepcopy(d)
                c.declared_type = self._rewrite_typeexpr(c.declared_type, {})
                out.append(c)
            # generic struct/enum templates and typealiases are dropped.

        # 2) functions: seed with every non-generic function (each keeps its
        #    name); generic functions are emitted only via reached instantiations.
        for name, sig in self.funcs.items():
            if not sig.type_params:
                self.fn_worklist.append((name, {}, name))
        while self.fn_worklist:
            orig, subst, mangled = self.fn_worklist.pop()
            if mangled in self.emitted_fns:
                continue
            self.emitted_fns[mangled] = self._specialize_fn(orig, subst, mangled)

        # 3) drain the generic-type worklist (stamping may enqueue more types).
        while self.type_worklist:
            t = self.type_worklist.pop()
            self.stamped_types.append(self._stamp_type(t))

        out.extend(self.stamped_types)
        out.extend(self.emitted_fns.values())
        # The program is already concrete, desugared, and prelude-free — re-check
        # it without re-injecting the prelude (its generic templates are gone).
        return check(ast.Program(out), with_prelude=False)

    # -- function specialization --------------------------------------------

    def _specialize_fn(self, orig: str, subst: dict[str, Type],
                       mangled: str) -> ast.FunDecl:
        clone = copy.deepcopy(self.funcs[orig].decl)
        clone.name = mangled
        clone.type_params = []
        for p in clone.params:
            p.type = self._rewrite_typeexpr(p.type, subst)
        if clone.ret_type is not None:
            clone.ret_type = self._rewrite_typeexpr(clone.ret_type, subst)
        # `#test` / `#main` attribute expressions reference types too.
        for attr in clone.attributes:
            attr.args = [self._rewrite(e, subst) for e in attr.args]
            if attr.outputs:
                attr.outputs = [self._rewrite(e, subst) for e in attr.outputs]
        clone.body = self._rewrite(clone.body, subst)
        return clone

    def _rewrite(self, node, subst: dict[str, Type]):
        """Walk a cloned subtree, rewriting calls, type annotations, and the
        name attributes the re-check needs to resolve. Returns the node, which
        may be *replaced* (a bare `None` becomes a qualified constructor)."""
        # enum constructors: rewrite to a qualified reference to the stamped
        # concrete enum so the re-check resolves the right (mangled) layout.
        if getattr(node, "enum_ctor", None) is not None:
            return self._rewrite_enum_ctor(node, subst)
        if isinstance(node, ast.Call):
            self._rewrite_fn_call(node, subst)
        elif isinstance(node, ast.StructLit):
            t = self._subst_type(getattr(node, "resolved_type", None), subst)
            if isinstance(t, StructType):
                node.type_name = self._aggregate_name(t)
        elif isinstance(node, ast.Match):
            scrut_t = self._subst_type(
                getattr(node.scrutinee, "resolved_type", None), subst)
            for arm in node.arms:
                self._rewrite_pattern(arm.pattern, scrut_t, subst)
        if isinstance(node, (ast.VarDecl, ast.DestructDecl)) and node.declared_type is not None:
            node.declared_type = self._rewrite_typeexpr(node.declared_type, subst)
        self._rewrite_kids(node, subst)
        return node

    def _rewrite_kids(self, node, subst: dict[str, Type]) -> None:
        for f in dataclasses.fields(node):
            setattr(node, f.name, self._rewrite_child(getattr(node, f.name), subst))

    def _rewrite_child(self, val, subst: dict[str, Type]):
        if isinstance(val, ast.Node):
            return self._rewrite(val, subst)
        if isinstance(val, list):
            return [self._rewrite_child(v, subst) for v in val]
        return val

    def _rewrite_fn_call(self, node: ast.Call, subst: dict[str, Type]) -> None:
        callee = node.callee
        if not isinstance(callee, ast.Name):
            return
        sig = self.funcs.get(callee.ident)
        if sig is None or not sig.type_params:
            return
        type_args = getattr(node, "type_args", None)
        if type_args is None:  # pragma: no cover - defensive
            return
        concrete = tuple(self._subst_type(a, subst) for a in type_args)
        node.callee = ast.Name(self._request_fn(callee.ident, concrete)).at(
            callee.line, callee.column
        )

    def _rewrite_enum_ctor(self, node, subst: dict[str, Type]):
        """Rewrite any enum constructor (`Enum.Variant(..)`, `Color.Red`, bare
        `Ok(x)`/`None`) to a qualified reference to the stamped concrete enum,
        so the re-check binds it to the right mangled layout."""
        t = self._subst_type(getattr(node, "resolved_type", None), subst)
        variant = node.enum_ctor[1]
        name = self._aggregate_name(t) if isinstance(t, EnumType) else node.enum_ctor[0]
        ln, col = node.line, node.column
        target = ast.Name(name).at(ln, col)
        if isinstance(node, ast.Call):
            node.callee = ast.FieldAccess(target, variant).at(ln, col)
            node.args = [self._rewrite_child(a, subst) for a in node.args]
            return node
        # FieldAccess (`Color.Red`) or bare Name (`None`): a no-payload variant.
        return ast.FieldAccess(target, variant).at(ln, col)

    def _rewrite_pattern(self, pat, t, subst: dict[str, Type]) -> None:
        if isinstance(pat, ast.PatEnum):
            if isinstance(t, EnumType):
                if pat.enum_name is not None:
                    pat.enum_name = self._aggregate_name(t)
                payload = self.checker._enum_variant_types(t).get(pat.variant, [])
                for sub, ft in zip(pat.elems, payload):
                    self._rewrite_pattern(sub, ft, subst)
        elif isinstance(pat, ast.PatStruct):
            if isinstance(t, StructType):
                pat.type_name = self._aggregate_name(t)
                fields = self.checker._struct_field_types(t)
                for fp in pat.fields:
                    self._rewrite_pattern(fp.pattern, fields.get(fp.name), subst)
        elif isinstance(pat, ast.PatTuple):
            if isinstance(t, TupleType):
                for sub, et in zip(pat.elems, t.elems):
                    self._rewrite_pattern(sub, et, subst)
        elif isinstance(pat, ast.PatOr):
            for alt in pat.alts:
                self._rewrite_pattern(alt, t, subst)

    def _request_fn(self, name: str, concrete: tuple[Type, ...]) -> str:
        key = (name, concrete)
        if key in self.fn_mono_name:
            return self.fn_mono_name[key]
        mangled = self._mangle(name, concrete)
        self.fn_mono_name[key] = mangled
        self.fn_worklist.append((name, dict(zip(self.funcs[name].type_params, concrete)), mangled))
        return mangled

    # -- type stamping -------------------------------------------------------

    def _stamp_type(self, t: Type) -> ast.Decl:
        if isinstance(t, StructType):
            decl = copy.deepcopy(self.checker.struct_decls[t.name])
            subst = dict(zip(decl.type_params, t.args))
            decl.name = self._mangle_type(t)
            decl.type_params = []
            for f in decl.fields:
                f.type = self._rewrite_typeexpr(f.type, subst)
            return decl
        assert isinstance(t, EnumType)
        decl = copy.deepcopy(self.checker.enum_decls[t.name])
        subst = dict(zip(decl.type_params, t.args))
        decl.name = self._mangle_type(t)
        decl.type_params = []
        for v in decl.variants:
            v.payload = [self._rewrite_typeexpr(p, subst) for p in v.payload]
        return decl

    def _request_type(self, t: Type) -> str:
        key = (t.name, t.args)
        if key in self.type_mono_name:
            return self.type_mono_name[key]
        mangled = self._mangle_type(t)
        self.type_mono_name[key] = mangled
        self.type_worklist.append(t)
        return mangled

    def _aggregate_name(self, t: Type) -> str:
        """The concrete name to use for an aggregate instance (stamping it if
        it is a generic instantiation)."""
        if isinstance(t, (StructType, EnumType)) and t.args:
            return self._request_type(t)
        return t.name

    # -- type <-> TypeExpr ---------------------------------------------------

    def _rewrite_typeexpr(self, texpr, subst: dict[str, Type]):
        """Resolve a source type annotation under `subst` and re-emit it as a
        concrete (possibly mangled) annotation."""
        return self._type_to_typeexpr(self._resolve_typeexpr(texpr, subst))

    def _resolve_typeexpr(self, texpr, subst: dict[str, Type]) -> Type:
        self.checker._type_params = frozenset(subst.keys())
        try:
            t = self.checker._resolve(texpr)
        finally:
            self.checker._type_params = frozenset()
        return self._subst_type(t, subst)

    def _type_to_typeexpr(self, t: Type):
        if isinstance(t, (IntType, BoolType, StrType, StringBuilderType)):
            return ast.TypeRef(type_name(t))
        if isinstance(t, TupleType):
            return ast.TupleTypeRef([self._type_to_typeexpr(e) for e in t.elems])
        if isinstance(t, ListType):
            return ast.ListTypeRef(self._type_to_typeexpr(t.elem))
        if isinstance(t, MapType):
            return ast.MapTypeRef(self._type_to_typeexpr(t.key),
                                  self._type_to_typeexpr(t.value))
        if isinstance(t, (StructType, EnumType)):
            return ast.TypeRef(self._aggregate_name(t))
        raise AssertionError(  # pragma: no cover - unresolved type parameter
            f"cannot reify type {t!r} during monomorphization"
        )

    def _subst_type(self, t: Type | None, subst: dict[str, Type]) -> Type | None:
        if isinstance(t, TypeParam):
            return subst.get(t.name, t)
        if isinstance(t, TupleType):
            return TupleType(tuple(self._subst_type(e, subst) for e in t.elems))
        if isinstance(t, ListType):
            return ListType(self._subst_type(t.elem, subst))
        if isinstance(t, MapType):
            return MapType(self._subst_type(t.key, subst),
                           self._subst_type(t.value, subst))
        if isinstance(t, StructType) and t.args:
            return StructType(t.name, tuple(self._subst_type(a, subst) for a in t.args))
        if isinstance(t, EnumType) and t.args:
            return EnumType(t.name, tuple(self._subst_type(a, subst) for a in t.args))
        return t

    # -- name mangling -------------------------------------------------------

    def _mangle(self, name: str, args: tuple[Type, ...]) -> str:
        return name + "__" + "_".join(self._mono_token(a) for a in args)

    def _mangle_type(self, t: Type) -> str:
        return t.name + "__" + "_".join(self._mono_token(a) for a in t.args)

    def _mono_token(self, t: Type) -> str:
        if isinstance(t, (IntType, BoolType, StrType, StringBuilderType)):
            return type_name(t)
        if isinstance(t, (StructType, EnumType)):
            return self._mangle_type(t) if t.args else t.name
        if isinstance(t, TupleType):
            return "T" + str(len(t.elems)) + "".join(
                "_" + self._mono_token(e) for e in t.elems
            )
        if isinstance(t, ListType):
            return "L_" + self._mono_token(t.elem)
        if isinstance(t, MapType):
            return "M_" + self._mono_token(t.key) + "_" + self._mono_token(t.value)
        return "X"  # pragma: no cover - defensive


def monomorphize(checker: Checker) -> Checker:
    """Return a checked, fully concrete copy of `checker`'s program (D13)."""
    return _Monomorphizer(checker).run()
