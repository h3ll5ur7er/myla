"""Module loader & linker (v0.5.1b).

Myla modules are an entirely *front-end* concern: this stage turns an entry file
plus its `import` graph into a single, flat `ast.Program` with globally-unique
declaration names, which the existing checker / interpreter / compiler consume
unchanged (docs/Architecture/Module-loader.md).

Pipeline:
    link(entry) -> load every reachable module once (memoized by canonical path)
                -> assign each module a unique id + qualify its top-level names
                -> resolve `pub` exports and `import` bindings
                -> rewrite every in-module reference to the qualified name
                -> concatenate all modules' declarations into one Program

Name model (D22/D54/D57):
  * a `.my` file is a **module**, a directory is a **package**; the dotted path
    mirrors the tree, with the leading-dot count selecting the search base.
  * the **entry** module keeps simple names (id ""); every other module M gets a
    unique id and its top-level name `n` becomes `f"{id}${n}"` (``$`` cannot
    appear in a source identifier, so qualified names never collide with user
    names, method keys, or the prelude).
  * `pub` marks a declaration exported; `from P import x` binds P's exported `x`;
    `import P [as p]` binds the module itself for `p.member` access; `pub`
    re-exports either kind.

A *binding* (the thing a name resolves to) is one of:
  * ``("decl", qualified_name)`` — a top-level declaration, or
  * ``("module", module_id)``    — a module, usable only via `name.member`.
"""
from __future__ import annotations

import dataclasses
import os
import re
from collections.abc import Sequence

from . import ast
from .errors import ModuleError, in_file
from .lexer import tokenize
from .parser import parse
from .tokens import KEYWORDS

# Roots that always resolve to the bundled standard library, never the project
# tree (D57: builtins are shadow-protected). The stdlib ships under
# `<package>/std/` (see `default_stdlib_root`) and may not be shadowed by a
# project directory.
_RESERVED_ROOTS = frozenset({"std"})

# A package's name: what imports start with (MYLA-92), the manifest's rule for
# `package.name` (Architecture/Project-tool); keywords are excluded as well.
_PACKAGE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


def default_stdlib_root() -> str:
    """The search base for the bundled standard library (v0.5.4).

    The stdlib modules live in `<this package>/std/*.my`, so the *base* a
    `from std.… import …` resolves against is the package directory itself
    (the loader then descends into the `std/` segment)."""
    return os.path.dirname(os.path.abspath(__file__))


class _Module:
    def __init__(self, mid: str, path: str, program: ast.Program, source: str):
        self.id = mid
        self.path = path
        self.source = source
        self.program = program
        self.imports: list[ast.ImportDecl] = [
            d for d in program.decls if isinstance(d, ast.ImportDecl)
        ]
        self.decls: list[ast.Decl] = [
            d for d in program.decls if not isinstance(d, ast.ImportDecl)
        ]
        # the real path of each import's module, in `imports` order (filled
        # while loading, so each import is resolved once)
        self.targets: list[str] = []
        # simple exported name -> binding (filled by the linker)
        self.exports: dict[str, tuple] = {}
        # name visible inside this module -> binding
        self.bindings: dict[str, tuple] = {}

    def qualify(self, name: str) -> str:
        return name if self.id == "" else f"{self.id}${name}"

    def env_decl(self) -> dict[str, str]:
        """`name -> qualified_name` for declaration bindings (the only ones a
        bare reference or type name can resolve to)."""
        return {n: b[1] for n, b in self.bindings.items() if b[0] == "decl"}

    def module_aliases(self) -> dict[str, str]:
        """`access_key -> module_id` for module bindings; the key is a simple
        alias (`import P as x` -> "x") or the full dotted path (`import a.b.c`
        -> "a.b.c")."""
        return {n: b[1] for n, b in self.bindings.items() if b[0] == "module"}


def _named_decls(m: _Module):
    """Yield this module's top-level *named* declarations (everything with a
    `name`: struct/enum/typealias/const/fun/trait — not `impl`)."""
    for d in m.decls:
        if isinstance(d, ast.ImplDecl):
            continue
        yield d


# --------------------------------------------------------------------------
# Path resolution (D22 search bases + D57 corner cases)
# --------------------------------------------------------------------------


def _search_bases(importer_path: str, path: ast.ImportPath, project_root: str,
                  stdlib_root: str | None) -> list[str]:
    if path.dots == 0:
        bases = [project_root]
        if stdlib_root is not None:
            bases.append(stdlib_root)
        return bases
    # `.` = current file's directory, `..` = its parent, etc.
    base = os.path.dirname(importer_path)
    for _ in range(path.dots - 1):
        base = os.path.dirname(base)
    return [base]


def _descend(base: str, segments: list[str], dotted: str,
             path: ast.ImportPath) -> str | None:
    """Resolve `base/seg0/seg1/.../segN` to a module file, or None if absent.

    Intermediate segments must be packages (directories); the final segment is a
    module file `segN.my` or a package directory whose root module is
    `segN/segN.my` (D57 rule 1). A file/dir name clash is an error (rule 2)."""
    cur = base
    for seg in segments[:-1]:
        nxt = os.path.join(cur, seg)
        if not os.path.isdir(nxt):
            return None
        cur = nxt
    last = segments[-1]
    file_cand = os.path.join(cur, last + ".my")
    dir_cand = os.path.join(cur, last)
    file_exists = os.path.isfile(file_cand)
    dir_exists = os.path.isdir(dir_cand)
    if file_exists and dir_exists:
        raise ModuleError(
            f"ambiguous import '{dotted}': both '{last}.my' and a package "
            f"'{last}/' exist in {cur}",
            at=path,
        )
    if file_exists:
        return os.path.realpath(file_cand)
    if dir_exists:
        pkg_root = os.path.join(dir_cand, last + ".my")
        if os.path.isfile(pkg_root):
            return os.path.realpath(pkg_root)
        raise ModuleError(
            f"package '{dotted}' has no package-root module "
            f"'{last}/{last}.my'",
            at=path,
        )
    return None


def _resolve_module_path(importer_path: str, path: ast.ImportPath,
                         project_root: str, stdlib_root: str | None,
                         packages: dict[str, str] | None = None) -> str:
    dotted = path.dotted()
    first = path.segments[0]
    if path.dots == 0 and first in _RESERVED_ROOTS:
        # Reserved roots resolve to the stdlib and may not be shadowed (D57 r4).
        if os.path.exists(os.path.join(project_root, first)):
            raise ModuleError(
                f"'{first}' is a reserved standard-library root and "
                f"cannot be shadowed by a project file or directory",
                at=path,
            )
    elif path.dots == 0 and packages and first in packages:
        # A package `geo` is looked up as if its directory were `geo/` in the
        # project root, which therefore may not have one (MYLA-92, D73 (6)).
        if os.path.exists(os.path.join(project_root, first)) or \
                os.path.exists(os.path.join(project_root, first + ".my")):
            raise ModuleError(
                f"'{first}' is a dependency and cannot be shadowed by a project "
                f"file or directory",
                at=path,
            )
        return _resolve_in_package(first, packages[first], path)
    for base in _search_bases(importer_path, path, project_root, stdlib_root):
        resolved = _descend(base, path.segments, dotted, path)
        if resolved is not None:
            return resolved
    raise ModuleError(f"cannot resolve import '{dotted}'", at=path)


def _resolve_in_package(name: str, pkg_dir: str, path: ast.ImportPath) -> str:
    """`name.rest` in the package `name` whose directory is `pkg_dir`: `name`
    alone is its root module `pkg_dir/name.my`, `name.b.c` is `pkg_dir/b/c.my`
    (or the package root `pkg_dir/b/c/c.my`)."""
    if len(path.segments) == 1:
        root = os.path.join(pkg_dir, name + ".my")
        if os.path.isfile(root):
            return os.path.realpath(root)
        raise ModuleError(
            f"package '{name}' has no root module '{name}.my' in {pkg_dir}", at=path
        )
    resolved = _descend(pkg_dir, path.segments[1:], path.dotted(), path)
    if resolved is None:
        raise ModuleError(f"cannot resolve import '{path.dotted()}'", at=path)
    return resolved


def parse_package_flag(text: str) -> tuple[str, str]:
    """`name=dir`, the value of a `--package` flag, as a (name, dir) pair for
    `link`; the name ends at the first `=`. `link` checks the pair."""
    name, eq, directory = text.partition("=")
    if not eq:
        raise ModuleError(f"malformed --package '{text}': expected name=dir")
    return name, directory


def _check_packages(packages: Sequence[tuple[str, str]]) -> dict[str, str]:
    """The packages as `name -> real directory`, or the first error in the
    list: a package named `std`, a name that can't start an import, a name
    given twice, a missing directory."""
    out: dict[str, str] = {}
    for name, directory in packages:
        if name in _RESERVED_ROOTS:
            raise ModuleError(f"a package cannot be named '{name}': it is the standard library")
        if not _PACKAGE_NAME.match(name) or name in KEYWORDS:
            raise ModuleError(f"invalid package name '{name}'")
        if name in out:
            raise ModuleError(f"package '{name}' is given twice")
        if directory == "":
            raise ModuleError(f"package '{name}' has no directory")
        if not os.path.isdir(directory):
            raise ModuleError(f"package '{name}': '{directory}' is not a directory")
        out[name] = os.path.realpath(directory)
    return out


def _under(parts: list[str], root: str) -> list[str] | None:
    """The segments of a path (split into `parts`) below `root`, if below."""
    rs = root.rstrip(os.sep).split(os.sep)
    return parts[len(rs):] if parts[:len(rs)] == rs else None


def _module_id(abspath: str, entry_path: str, project_root: str,
               stdlib_root: str | None = None,
               packages: Sequence[tuple[str, str]] = ()) -> str:
    """The id prefixing a module's global names, by the self-hosted loader's
    rules (selfhost/loader.my, `module_id`): "" for the entry, the path under
    the stdlib root for the standard library, a package's name and the path
    under its directory for a package (as if the directory were `<name>/` in
    the project root, MYLA-92: no fetch paths in names), the path under the
    project root for the project, and above it one `up` per level climbed
    (MYLA-81: `../x` and `x` no longer collide, and both toolchains name things
    alike)."""
    if abspath == entry_path:
        return ""
    parts = abspath.split(os.sep)
    if stdlib_root:
        rest = _under(parts, stdlib_root)
        if rest is not None:
            return _module_tag(rest)
    best: list[str] | None = None        # the innermost package directory wins
    for name, pkg_dir in packages:
        rest = _under(parts, pkg_dir)
        if rest is not None and (best is None or len(rest) + 1 < len(best)):
            best = [name, *rest]
    if best is not None:
        return _module_tag(best)
    rest = _under(parts, project_root)
    if rest is not None:
        return _module_tag(rest)
    rs = project_root.rstrip(os.sep).split(os.sep)
    common = 0
    while common < min(len(parts), len(rs)) and parts[common] == rs[common]:
        common += 1
    return _module_tag(["up"] * (len(rs) - common) + parts[common:])


def _module_tag(parts: list[str]) -> str:
    """Path segments as a `$`-joined tag valid in qualified names and assembly
    labels (`.my` dropped, each run of other characters one `$`)."""
    rel = "/".join(parts)
    if rel.endswith(".my"):
        rel = rel[:-3]
    return re.sub(r"[^A-Za-z0-9_]+", "$", rel).strip("$")


# --------------------------------------------------------------------------
# Reference rewriting (scope-aware): simple name -> qualified global name
# --------------------------------------------------------------------------


class _Renamer:
    """Rewrites every in-module reference whose simple name resolves to a module
    global (own decl or imported name) into its qualified form, and folds
    `module.member` field-access chains into the qualified target. Names
    shadowed by a local binding, builtins, and prelude names are left
    untouched."""

    def __init__(self, env_decl: dict[str, str], module_aliases: dict[str, str],
                 module_exports: dict[str, dict[str, tuple]]):
        self.env = env_decl
        self.module_aliases = module_aliases
        self.module_exports = module_exports
        self.value_locals: set[str] = set()
        self.type_locals: set[str] = set()

    # -- declarations --
    def rename_module(self, m: _Module) -> None:
        for d in m.decls:
            self._decl(d, m)

    def _decl(self, d: ast.Decl, m: _Module) -> None:
        if isinstance(d, ast.StructDecl):
            d.name = m.qualify(d.name)
            self.type_locals = set(d.type_params)
            for f in d.fields:
                self._type(f.type)
            self.type_locals = set()
        elif isinstance(d, ast.EnumDecl):
            d.name = m.qualify(d.name)
            self.type_locals = set(d.type_params)
            for v in d.variants:
                for t in v.payload:
                    self._type(t)
            self.type_locals = set()
        elif isinstance(d, ast.TypeAliasDecl):
            d.name = m.qualify(d.name)
            self._type(d.target)
        elif isinstance(d, ast.ConstDecl):
            d.name = m.qualify(d.name)
            self._type(d.declared_type)
            self.value_locals = set()
            d.value = self._expr(d.value)
        elif isinstance(d, ast.FunDecl):
            d.name = m.qualify(d.name)
            self._function(d)
        elif isinstance(d, ast.TraitDecl):
            d.name = m.qualify(d.name)
            for meth in d.methods:
                self.type_locals = set(meth.type_params) | {"Self"}
                self._signature_types(meth)
                self.type_locals = set()
        elif isinstance(d, ast.ImplDecl):
            self.type_locals = set(d.type_params) | {"Self"}
            self._type(d.target)
            if d.trait_name is not None and d.trait_name in self.env \
                    and d.trait_name not in self.type_locals:
                d.trait_name = self.env[d.trait_name]
            self._rewrite_bounds(d.type_param_bounds)
            self.type_locals = set()
            for meth in d.methods:
                self._function(meth, receiver=True, impl_params=d.type_params)

    def _rewrite_bounds(self, bounds: dict) -> None:
        for param, traits in bounds.items():
            bounds[param] = [
                self.env[t] if t in self.env else t for t in traits
            ]

    def _signature_types(self, fn: ast.FunDecl) -> None:
        for p in fn.params:
            self._type(p.type)
        if fn.ret_type is not None:
            self._type(fn.ret_type)

    def _function(self, fn: ast.FunDecl, *, receiver: bool = False,
                  impl_params: list[str] | None = None) -> None:
        saved_t = self.type_locals
        self.type_locals = set(fn.type_params) | set(impl_params or []) | {"Self"}
        self._signature_types(fn)
        # `#test` cases are expressions in the module's scope (MYLA-11)
        self.value_locals = set()
        for attr in fn.attributes:
            if attr.name == "test":
                attr.args = [self._expr(a) for a in attr.args]
                if attr.outputs is not None:
                    attr.outputs = [self._expr(o) for o in attr.outputs]
        self.value_locals = {p.name for p in fn.params}
        if receiver:
            self.value_locals.add("self")
        self._rewrite_bounds(fn.type_param_bounds)
        if fn.body is not None:
            self._block(fn.body)
        self.value_locals = set()
        self.type_locals = saved_t

    # -- types --
    def _type(self, t) -> None:
        if t is None:
            return
        if isinstance(t, ast.TypeRef):
            if t.name not in self.type_locals and t.name in self.env:
                t.name = self.env[t.name]
            for a in t.args:
                self._type(a)
        elif isinstance(t, ast.TupleTypeRef):
            for e in t.elems:
                self._type(e)
        elif isinstance(t, ast.ListTypeRef):
            self._type(t.elem)
        elif isinstance(t, ast.MapTypeRef):
            self._type(t.key)
            self._type(t.value)
        elif isinstance(t, ast.FnTypeRef):
            for p in t.params:
                self._type(p)
            self._type(t.ret)

    # -- statements --
    def _block(self, block: ast.Block) -> None:
        saved = set(self.value_locals)
        for stmt in block.statements:
            self._stmt(stmt)
        self.value_locals = saved

    def _stmt(self, s) -> None:
        if isinstance(s, ast.VarDecl):
            s.init = self._expr(s.init)
            self._type(s.declared_type)
            self.value_locals.add(s.name)
        elif isinstance(s, ast.DestructDecl):
            s.init = self._expr(s.init)
            self._type(s.declared_type)
            for name in _binding_names(s.binding):
                self.value_locals.add(name)
        elif isinstance(s, ast.Assign):
            s.target = self._expr(s.target)
            s.value = self._expr(s.value)
        elif isinstance(s, ast.If):
            s.cond = self._expr(s.cond)
            self._block(s.then)
            if isinstance(s.otherwise, ast.Block):
                self._block(s.otherwise)
            elif isinstance(s.otherwise, ast.If):
                self._stmt(s.otherwise)
        elif isinstance(s, ast.While):
            s.cond = self._expr(s.cond)
            self._block(s.body)
        elif isinstance(s, ast.For):
            s.start = self._expr(s.start)
            s.end = self._expr(s.end)
            s.iterable = self._expr(s.iterable)
            saved = set(self.value_locals)
            self.value_locals.add(s.var_name)
            self._block(s.body)
            self.value_locals = saved
        elif isinstance(s, ast.Return):
            s.value = self._expr(s.value)
        elif isinstance(s, ast.ExprStmt):
            s.expr = self._expr(s.expr)
        elif isinstance(s, ast.Block):
            self._block(s)
        # Break / Continue: nothing to rewrite.

    # -- expressions (return-style: may replace the node) --
    def _expr(self, e):
        if e is None:
            return None
        if isinstance(e, ast.Name):
            if e.ident not in self.value_locals and e.ident in self.env:
                e.ident = self.env[e.ident]
            elif e.ident not in self.value_locals and e.ident in self.module_aliases:
                raise ModuleError(
                    f"module '{e.ident}' cannot be used as a value — access a "
                    f"member with '{e.ident}.<name>'",
                    at=e,
                )
            return e
        if isinstance(e, ast.Unary):
            e.operand = self._expr(e.operand)
            return e
        if isinstance(e, ast.Await):
            e.operand = self._expr(e.operand)
            return e
        if isinstance(e, ast.Binary):
            e.left = self._expr(e.left)
            e.right = self._expr(e.right)
            return e
        if isinstance(e, ast.Call):
            e.callee = self._expr(e.callee)
            e.args = [self._expr(a) for a in e.args]
            return e
        if isinstance(e, ast.FieldAccess):
            repl = self._try_module_access(e)
            if repl is not None:
                return repl
            e.target = self._expr(e.target)
            return e
        if isinstance(e, ast.StructLit):
            if e.type_name not in self.type_locals and e.type_name in self.env:
                e.type_name = self.env[e.type_name]
            for fi in e.fields:
                fi.value = self._expr(fi.value)
            return e
        if isinstance(e, ast.TupleLit):
            e.elems = [self._expr(x) for x in e.elems]
            return e
        if isinstance(e, ast.TupleIndex):
            e.target = self._expr(e.target)
            return e
        if isinstance(e, ast.ListLit):
            e.elems = [self._expr(x) for x in e.elems]
            return e
        if isinstance(e, ast.MapLit):
            e.entries = [(self._expr(k), self._expr(v)) for k, v in e.entries]
            return e
        if isinstance(e, ast.Index):
            e.target = self._expr(e.target)
            e.index = self._expr(e.index)
            return e
        if isinstance(e, ast.Match):
            self._match(e)
            return e
        if isinstance(e, ast.Try):
            e.operand = self._expr(e.operand)
            return e
        if isinstance(e, ast.Cast):
            e.operand = self._expr(e.operand)
            self._type(e.target)
            return e
        if isinstance(e, ast.Lambda):
            saved = set(self.value_locals)
            for p in e.params:
                self._type(p.type)
                self.value_locals.add(p.name)
            if isinstance(e.body, ast.Block):
                self._block(e.body)
            else:
                e.body = self._expr(e.body)
            self.value_locals = saved
            return e
        return e  # literals / Hole

    def _try_module_access(self, e: ast.FieldAccess):
        """If `e` is a `module.member[.…]` chain, fold the module prefix into the
        qualified target and return the rewritten node; else None."""
        names: list[str] = []
        accesses: list[ast.FieldAccess] = []
        cur = e
        while isinstance(cur, ast.FieldAccess):
            names.append(cur.field_name)
            accesses.append(cur)
            cur = cur.target
        if not isinstance(cur, ast.Name):
            return None
        root = cur
        if root.ident in self.value_locals:
            return None
        seg_names = list(reversed(names))  # e.g. ["b", "c", "member"]
        # Longest module-alias prefix wins: try root, root.b, root.b.c, …
        match_k = None
        for k in range(len(seg_names), -1, -1):
            cand = ".".join([root.ident] + seg_names[:k])
            if cand in self.module_aliases:
                match_k = k
                break
        if match_k is None:
            return None
        mid = self.module_aliases[".".join([root.ident] + seg_names[:match_k])]
        rest = seg_names[match_k:]
        if not rest:
            raise ModuleError(
                f"module '{'.'.join([root.ident] + seg_names[:match_k])}' cannot "
                f"be used as a value — access a member with '.<name>'",
                at=root,
            )
        qualified, remaining = self._resolve_member_chain(mid, rest, root)
        # each new node spans the access it replaces (MYLA-65)
        replaced = list(reversed(accesses))[len(seg_names) - len(remaining) - 1:]
        node = ast.Name(qualified).at(root.line, root.column)
        node.span = replaced[0].span
        for seg, access in zip(remaining, replaced[1:]):
            node = ast.FieldAccess(node, seg).at(root.line, root.column)
            node.span = access.span
        return node

    def _resolve_member_chain(self, mid: str, members: list[str], pos):
        """Walk `members` through module exports, returning (qualified_decl,
        leftover_members) where the leftover are ordinary field accesses on the
        resolved value."""
        cur_mid = mid
        i = 0
        while i < len(members):
            name = members[i]
            exports = self.module_exports.get(cur_mid, {})
            if name not in exports:
                raise ModuleError(
                    f"module does not export '{name}' (declarations are private "
                    f"unless marked 'pub')",
                    at=pos,
                )
            kind, value = exports[name]
            i += 1
            if kind == "decl":
                return value, members[i:]
            cur_mid = value  # a re-exported sub-module; keep walking
        raise ModuleError(
            "a module reference must end in a member access",
            at=pos,
        )

    def _match(self, m: ast.Match) -> None:
        m.scrutinee = self._expr(m.scrutinee)
        for arm in m.arms:
            saved = set(self.value_locals)
            self._pattern(arm.pattern)
            for name in _pattern_binds(arm.pattern):
                self.value_locals.add(name)
            arm.guard = self._expr(arm.guard)
            if isinstance(arm.body, ast.Block):
                self._block(arm.body)
            else:
                arm.body = self._expr(arm.body)
            self.value_locals = saved

    def _pattern(self, p) -> None:
        """Rewrite type names inside a pattern (enum/struct names)."""
        if isinstance(p, ast.PatLiteral):
            p.literal = self._expr(p.literal)
        elif isinstance(p, ast.PatEnum):
            if p.enum_name and p.enum_name not in self.type_locals \
                    and p.enum_name in self.env:
                p.enum_name = self.env[p.enum_name]
            for e in p.elems:
                self._pattern(e)
        elif isinstance(p, ast.PatTuple):
            for e in p.elems:
                self._pattern(e)
        elif isinstance(p, ast.PatStruct):
            if p.type_name not in self.type_locals and p.type_name in self.env:
                p.type_name = self.env[p.type_name]
            for fp in p.fields:
                self._pattern(fp.pattern)
        elif isinstance(p, ast.PatOr):
            for alt in p.alts:
                self._pattern(alt)
        # PatWildcard / PatBinding: no type names.


def _binding_names(b) -> list[str]:
    if isinstance(b, ast.BindName):
        return [b.name]
    if isinstance(b, ast.BindTuple):
        names: list[str] = []
        for e in b.elems:
            names.extend(_binding_names(e))
        return names
    return []  # BindWildcard


def _pattern_binds(p) -> list[str]:
    if isinstance(p, ast.PatBinding):
        return [p.name]
    if isinstance(p, ast.PatEnum):
        names: list[str] = []
        for e in p.elems:
            names.extend(_pattern_binds(e))
        return names
    if isinstance(p, ast.PatTuple):
        names = []
        for e in p.elems:
            names.extend(_pattern_binds(e))
        return names
    if isinstance(p, ast.PatStruct):
        names = []
        for fp in p.fields:
            names.extend(_pattern_binds(fp.pattern))
        return names
    if isinstance(p, ast.PatOr):
        return _pattern_binds(p.alts[0]) if p.alts else []
    return []


# --------------------------------------------------------------------------
# Linking
# --------------------------------------------------------------------------


def link(
    entry_path: str,
    *,
    stdlib_root: str | None = None,
    source_overrides: dict[str, str] | None = None,
    packages: Sequence[tuple[str, str]] | None = None,
    project_root: str | None = None,
) -> ast.Program:
    """Resolve the import graph rooted at `entry_path` and return one flat,
    name-qualified `ast.Program` ready for `types.check`.

    `source_overrides` maps a file path to in-memory source text; when a module
    to be loaded matches one of those paths, its text is used instead of reading
    from disk. This lets tools (e.g. the language server) type-check unsaved
    editor buffers without touching the filesystem. Keys are normalized with
    `os.path.realpath`, matching how modules are keyed internally.

    `packages` lists the build's dependencies as (name, directory) pairs, the
    `--package name=dir` flags (MYLA-92): an import `name.b.c` resolves in the
    directory as if it were `name/` in the project root. `project_root` is the
    base of imports without dots; it defaults to the entry file's directory
    (D57), and the project tool sets it to `src/` for nested files."""
    entry_abs = os.path.realpath(entry_path)
    if project_root is None:
        project_root = os.path.dirname(entry_abs)
    else:
        project_root = os.path.realpath(project_root)
    package_dirs = _check_packages(packages or ())
    overrides = {
        os.path.realpath(p): text for p, text in (source_overrides or {}).items()
    }

    modules: dict[str, _Module] = {}
    order: list[_Module] = []

    def load(abspath: str) -> _Module:
        if abspath in modules:
            return modules[abspath]
        if abspath in overrides:
            source = overrides[abspath]
        else:
            try:
                with open(abspath, "r", encoding="utf-8") as fh:
                    source = fh.read()
            except OSError as exc:
                raise ModuleError(f"cannot read module '{abspath}': {exc}")
        with in_file(abspath):
            program = parse(tokenize(source))
        mid = _module_id(abspath, entry_abs, project_root, stdlib_root,
                         list(package_dirs.items()))
        m = _Module(mid, abspath, program, source)
        modules[abspath] = m
        order.append(m)
        for imp in m.imports:
            with in_file(abspath):
                target = _resolve_module_path(
                    abspath, imp.path, project_root, stdlib_root, package_dirs
                )
            m.targets.append(target)
            load(target)
        return m

    load(entry_abs)
    _check_id_collisions(order)
    _build_exports(modules, order)
    _build_bindings(modules, order)

    module_exports = {m.id: m.exports for m in order}
    for m in order:
        with in_file(m.path):
            _Renamer(m.env_decl(), m.module_aliases(), module_exports).rename_module(m)

    merged: list[ast.Decl] = []
    for m in order:
        _mark_source_path(m)
        merged.extend(m.decls)
    return ast.Program(merged)


def _mark_source_path(m: _Module) -> None:
    """Record the file each declaration (and method) comes from as
    `source_path`: the checker and interpreter attribute errors to it (MYLA-10),
    the native backend emits debug line tables against it (MYLA-71)."""
    for d in m.decls:
        d.source_path = m.path
        if isinstance(d, ast.ImplDecl):
            for method in d.methods:
                method.source_path = m.path
        for lam in _lambdas(d):
            lam.source_path = m.path


def _lambdas(node):
    """Every lambda in `node`'s subtree."""
    if isinstance(node, list):
        for item in node:
            yield from _lambdas(item)
    elif isinstance(node, ast.Node):
        if isinstance(node, ast.Lambda):
            yield node
        for f in dataclasses.fields(node):
            yield from _lambdas(getattr(node, f.name))


def _check_id_collisions(order: list[_Module]) -> None:
    seen: dict[str, str] = {}
    for m in order:
        if m.id == "":
            continue
        if m.id in seen and seen[m.id] != m.path:
            raise ModuleError(
                f"module id collision '{m.id}' between {seen[m.id]} and "
                f"{m.path}"
            )
        seen[m.id] = m.path


def _build_exports(modules, order) -> None:
    # Base exports: a module's own `pub` declarations.
    for m in order:
        for d in _named_decls(m):
            if getattr(d, "is_pub", False):
                m.exports[d.name] = ("decl", m.qualify(d.name))
    # Re-exports (`pub from P import x` / `pub import P as x`): iterate to a
    # fixpoint so chained re-exports settle.
    changed = True
    while changed:
        changed = False
        for m in order:
            for imp, target in zip(m.imports, m.targets):
                if not imp.is_pub:
                    continue
                src = modules[target]
                if imp.items is None:
                    # pub import P as x -> re-export the module under `x`.
                    name = imp.alias  # parser guarantees `as` on a pub import
                    binding = ("module", src.id)
                    if m.exports.get(name) != binding:
                        m.exports[name] = binding
                        changed = True
                    continue
                for item in imp.items:
                    name = item.alias or item.name
                    if item.name not in src.exports:
                        continue  # may settle on a later pass
                    binding = src.exports[item.name]
                    if m.exports.get(name) != binding:
                        m.exports[name] = binding
                        changed = True


def _build_bindings(modules, order) -> None:
    for m in order:
        bindings: dict[str, tuple] = {}
        for d in _named_decls(m):
            bindings[d.name] = ("decl", m.qualify(d.name))
        with in_file(m.path):
            for imp, target in zip(m.imports, m.targets):
                _apply_import(imp, bindings, modules[target])
        m.bindings = bindings


def _bind(bindings: dict, name: str, binding: tuple, imp: ast.ImportDecl) -> None:
    if name in bindings and bindings[name] != binding:
        raise ModuleError(
            f"import of '{name}' collides with an existing name in this module "
            f"— rename with 'as'",
            at=imp,
        )
    bindings[name] = binding


def _apply_import(imp, bindings, src: _Module) -> None:
    if imp.items is None:
        # whole-module `import a.b.c [as x]`: bind the module for member access.
        key = imp.alias if imp.alias is not None else imp.path.dotted().lstrip(".")
        _bind(bindings, key, ("module", src.id), imp)
        return
    for item in imp.items:
        bound = item.alias or item.name
        if item.name not in src.exports:
            raise ModuleError(
                f"module '{imp.path.dotted()}' does not export '{item.name}' "
                f"(declarations are private unless marked 'pub')",
                at=imp,
            )
        _bind(bindings, bound, src.exports[item.name], imp)
