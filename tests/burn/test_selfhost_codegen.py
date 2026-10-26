"""Differential burn test for the self-hosted code generator (self-hosting v0.9).

`selfhost/codegen.my` is the Myla-written x86-64 backend and
`selfhost/gen_main.my` the thin driver: it loads and links a program's modules,
type-checks it (with the same `Option`/`Result`/`get` prelude the Python `run`
injects), generates GAS assembly, and writes that assembly to
stdout. A host wrapper then runs `as`/`ld` over it to produce a real ELF binary
(§4 of docs/self-hosting.md).

This test closes the v0.9 *codegen* parity gate: for every runnable example in
the corpus, the binary produced by the self-hosted backend must have the same
(stdout, exit code) as the Python oracle (`myla run`, the tree-walking
interpreter).

How the assembly is produced. The self-hosted compiler is itself a Myla
program. Where the host can build a native binary we compile `gen_main.my` once
(with the Python backend) and invoke that binary per example, which is fast;
otherwise we run the compiler's source through the Python interpreter. Either
way the *assembly under test* is emitted by the Myla-written backend — only the
way we run that backend differs.

Scope. The corpus gate covers the single-file top-level examples (`floats.my`
included since MYLA-29). Multi-module programs (`examples/modules` and the
projects in MODULE_PROJECTS) go through the self-hosted module loader (MYLA-30)
and are compared with the Python `link` + interpreter; MODULE_ERRORS pins the
loader's diagnostics to the Python loader's.
"""
from __future__ import annotations

import glob
import io
import os
import subprocess
import sys
import tempfile
import unittest

from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.loader import default_stdlib_root, link
from myla.parser import parse
from myla.types import check

from ._native import CAN_BUILD_NATIVE, SKIP_REASON

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
GEN_TOOL = os.path.join(_REPO, "selfhost", "gen_main.my")

# Examples outside the v0.9 codegen gate's scope (see module docstring).
EXCLUDED: set[str] = set()

# Programs of the Python backend's parity suite (test_compiler_parity.PROGRAMS)
# for bugs both backends had: the value of a store is evaluated before the
# container is touched, so `?` and `push(xs, pop(xs))` see no half-made slot
# (MYLA-4); an assignment to any place unshares the containers on its path
# (MYLA-3); a match binding keeps its value when the arm writes to the
# scrutinee's variable (MYLA-2); destructuring reads boxed enum leaves through
# their pointer (MYLA-21); closure environments own their captures (MYLA-22);
# floats (MYLA-29); `?` in a lambda checked against the lambda (MYLA-72); a
# `panic` arm of a match that yields an aggregate (MYLA-28); const references
# (MYLA-27), `remove` on a shared map (MYLA-25), partial application of
# aggregates (MYLA-26), derived `Eq` on recursive enums (MYLA-23), integer
# literals of 2^63 and above (MYLA-73), the int64 minimum divided by -1 (MYLA-5),
# saturating float -> integer casts (MYLA-6), left-to-right evaluation (MYLA-8),
# partial application evaluating its arguments once (MYLA-75), derived Eq on
# char and float fields (MYLA-13).
PARITY_PROGRAMS = (
    "try_inside_push_leaves_the_list_intact",
    "try_inside_map_insert_leaves_the_map_intact",
    "try_inside_append_byte_leaves_the_builder_intact",
    "push_evaluates_its_value_before_the_list",
    "assign_replaces_map_and_builder_elements",
    "assign_heap_owning_struct_to_any_place",
    "assign_heap_owning_struct_to_itself",
    "assign_to_a_field_of_a_shared_element_copies_it",
    "match_binding_survives_writes_to_the_scrutinee",
    "destructure_boxed_enum_and_list_leaves",
    "closure_environments_own_their_captures",
    "floats_in_depth",
    "try_in_lambdas_checks_against_the_lambda",
    "diverging_arm_of_an_aggregate_match",
    "consts_fold_through_references",
    "remove_leaves_map_copies_alone",
    "partial_application_of_aggregates",
    "derived_eq_on_recursive_enums",
    "big_integer_literals",
    "int64_min_divided_by_minus_one",
    "float_to_int_casts_saturate",
    "evaluation_order_is_left_to_right",
    "partial_application_evaluates_its_arguments_once",
    "derived_eq_on_char_and_float_fields",
)

# The Python backend's arena-reclaim stress programs (test_compiler_parity),
# with their expected output. The self-hosted arena is 4 GiB, so rather than
# "doesn't run out", each program must also stay under PEAK_LIMIT_MB: they
# allocate and drop millions of cells, and without `free` they need 34 MB to
# over 4 GiB (with it, 8 to 18 MB) (MYLA-22).
STRESS_PROGRAMS = {
    "STRESS_SRC": "354000000",
    "STRESS_TRY_SRC": "100000",
    "STRESS_TRY_AFTER_STAGED_VALUE_SRC": "7500000",
    "STRESS_LOOPCTL_SRC": "200001\n133333",
    "STRESS_LIST_SRC": "0",
    "STRESS_MAP_SRC": "0",
    "STRESS_MAP_REMOVE_SRC": "2399994",
    "STRESS_SB_SRC": "0",
    "STRESS_CLOSURE_SRC": "0",
    "STRESS_PARTIAL_SRC": "0",
    "STRESS_TRAIT_DISPATCH_SRC": "600000",
    "STRESS_FRAGMENTED_FREE_SRC": "38000",
}
PEAK_LIMIT_MB = 30

# Multi-module programs (MYLA-30): the self-hosted loader links modules the way
# the Python one does: per-module names (`id$name`), `pub` exports and
# re-exports, module aliases, nested modules and packages. Each project is
# written to a temporary directory; `main.my` is the entry.
MODULE_PROJECTS = {
    # `#test` cases in an imported module name its declarations (MYLA-11)
    "test_attributes_name_module_declarations": {
        "main.my": "from .lib import double\nfun main() {\n    print(double(4))\n}\n",
        "lib.my": (
            "pub const LIMIT: int = 10\nstruct P { x: int }\nenum E { A(int), B }\n"
            "fun val(e: E) -> int {\n    return match e { A(n) => n, B => 0 }\n}\n"
            "#test(LIMIT)[20]\n#test(P { x: LIMIT }.x)[val(E.A(20))]\n"
            "pub fun double(x: int) -> int {\n    return x * 2\n}\n"),
    },
    # MYLA-30's repro: a user `collect` next to std.process's private one
    "private_std_helper_name": {
        "main.my": (
            "from std.process import args\n"
            "fun collect(n: int) -> int {\n    return n * 2\n}\n"
            "fun main() {\n    print(collect(len(args()) as int))\n}\n"),
    },
    # the same private name in three modules
    "private_names_per_module": {
        "main.my": (
            "from .a import fa\nfrom .b import fb\n"
            "fun helper() -> int {\n    return 100\n}\n"
            "fun main() {\n    print(fa() + fb() + helper())\n}\n"),
        "a.my": "fun helper() -> int {\n    return 1\n}\npub fun fa() -> int {\n    return helper()\n}\n",
        "b.my": "fun helper() -> int {\n    return 2\n}\npub fun fb() -> int {\n    return helper() * 10\n}\n",
    },
    # aliases, nested modules, a package, enum constructors through an alias
    "aliases_and_packages": {
        "main.my": (
            "import .shapes as sh\n"
            "from .util.mathx import square, Pair\n"
            "import .util.mathx as mx\n"
            "import .geo as g\n"
            "fun main() {\n"
            "    let p = Pair { a: 3, b: 4 }\n"
            "    print(square(p.a) + mx.square(p.b))\n"
            "    print(sh.area(sh.Shape.Rect(2, 5)))\n"
            "    let s = sh.unit()\n"
            "    print(match s { Rect(w, h) => w * h, Circle(r) => r })\n"
            "    print(g.dist(g.origin()))\n}\n"),
        "shapes.my": (
            "pub enum Shape { Circle(int), Rect(int, int) }\n"
            "pub fun area(s: Shape) -> int {\n"
            "    return match s { Circle(r) => 3 * r * r, Rect(w, h) => w * h }\n}\n"
            "pub fun unit() -> Shape {\n    return Shape.Circle(1)\n}\n"),
        "util/mathx.my": (
            "pub struct Pair { a: int, b: int }\n"
            "pub fun square(x: int) -> int {\n    return x * x\n}\n"),
        "geo/geo.my": (
            "pub struct P { x: int, y: int }\n"
            "pub fun origin() -> P {\n    return P { x: 0, y: 0 }\n}\n"
            "pub fun dist(p: P) -> int {\n    return p.x + p.y + 42\n}\n"),
    },
    # types, methods, traits, generics and consts across modules, re-exports
    "types_methods_traits_generics": {
        "main.my": (
            "from .lib import Point, Shape, first, LIMIT, Area, deep\n"
            "fun total(xs: [Point]) -> int {\n"
            "    var n = 0\n    for x in xs { n = n + x.area() }\n    return n\n}\n"
            "fun main() {\n"
            "    let p = Point { x: 1, y: 2 }\n"
            "    print(p.sum())\n"
            "    let s = Shape.Line(p, Point { x: 5, y: 5 })\n"
            "    print(match s { Dot(q) => q.x, Line(a, b) => a.x + b.y })\n"
            "    print(first([LIMIT, 1]))\n"
            "    print(total([p, Point { x: 3, y: 3 }]))\n"
            "    print(deep())\n"
            "    let q = p + Point { x: 10, y: 20 }\n"
            "    print(q.y)\n}\n"),
        "lib/lib.my": (
            "pub from .inner import deep\n"
            "pub trait Area {\n    fun area(self) -> int\n}\n"
            "pub struct Point { x: int, y: int }\n"
            "impl Point {\n    fun sum(self) -> int {\n        return self.x + self.y\n    }\n}\n"
            "impl Area for Point {\n    fun area(self) -> int {\n        return self.x * self.y\n    }\n}\n"
            "impl Add for Point {\n    fun add(self, other: Point) -> Point {\n"
            "        return Point { x: self.x + other.x, y: self.y + other.y }\n    }\n}\n"
            "pub enum Shape { Dot(Point), Line(Point, Point) }\n"
            "pub fun first<T>(xs: [T]) -> T {\n    return xs[0]\n}\n"
            "pub const LIMIT: int = 7\n"),
        "lib/inner.my": "pub fun deep() -> int {\n    return 99\n}\n",
    },
    # locals, parameters, loop variables, match and lambda bindings and type
    # parameters shadow module-level names (in a non-entry module, where the
    # module names are qualified)
    "locals_shadow_module_names": {
        "main.my": (
            'import .lib\n'
            'from .lib import Box\n'
            'fun local_alias() -> int {\n'
            '    let lib = Box { v: 4 }\n'
            '    return lib.v\n'
            '}\n'
            'fun main() {\n'
            '    print(lib.shadowing(1))\n'
            '    print(lib.captures())\n'
            '    print(lib.generic(9))\n'
            '    print(lib.unbox(Box { v: 6 }))\n'
            '    print(local_alias())\n'
            '}\n'
        ),
        "lib.my": (
            'pub struct Box { v: int }\n'
            'fun helper() -> int {\n'
            '    return 1000\n'
            '}\n'
            'fun count() -> int {\n'
            '    return 5\n'
            '}\n'
            'fun one() -> int {\n'
            '    return 1\n'
            '}\n'
            'fun two() -> int {\n'
            '    return 2\n'
            '}\n'
            'pub fun shadowing(count: int) -> int {\n'
            '    let helper = 3\n'
            '    var total = count + helper\n'
            '    for count in 0..3 {\n'
            '        total = total + count\n'
            '    }\n'
            '    let f = (helper: int) => helper * 2\n'
            '    total = total + f(10)\n'
            '    let o: Option<int> = Some(7)\n'
            '    total = total + match o {\n'
            '        Some(count) => count,\n'
            '        None => 0,\n'
            '    }\n'
            '    let (one, two) = (100, 200)\n'
            '    return total + one + two\n'
            '}\n'
            'pub fun captures() -> int {\n'
            '    let add = (x: int) => x + count() + helper()\n'
            '    return add(1)\n'
            '}\n'
            'pub fun generic<Box>(x: Box) -> Box {\n'
            '    return x\n'
            '}\n'
            'pub fun unbox(b: Box) -> int {\n'
            '    return b.v\n'
            '}\n'
        ),
    },
}

# Programs the loader rejects (MYLA-30), and lex, parse and type errors in
# imported modules (MYLA-28): the self-hosted compiler prints the Python CLI's
# diagnostic (message, file, position, source line and caret).
MODULE_ERRORS = {
    "parse_error_in_module": {
        "main.my": "import lib\nfun main() {\n    print(lib.f())\n}\n",
        "lib.my": "pub fun f() -> int {\n    return 1 +\n}\n",
    },
    "lex_error_in_module": {
        "main.my": "from .lib import f\nfun main() {\n    print(f())\n}\n",
        "lib.my": "pub fun f() -> int {\n    return 0x\n}\n",
    },
    "parse_error_in_entry": {"main.my": "fun main() {\n    let x = \n}\n"},
    # type errors (MYLA-28): attributed to the file of the declaration
    "type_error_in_entry": {"main.my": "fun main() {\n    let x: int = \"s\"\n}\n"},
    "type_error_in_module": {
        "main.my": "import lib\nfun main() {\n    print(lib.f())\n}\n",
        "lib.my": "pub fun f() -> int {\n    return \"s\"\n}\n",
    },
    "type_error_in_method_of_module": {
        "main.my": "from .lib import P\nfun main() {\n    print(P { x: 1 }.get())\n}\n",
        "lib.my": "pub struct P { x: int }\nimpl P {\n    fun get(self) -> int {\n        return self.y\n    }\n}\n",
    },
    "field_type_error_in_module": {
        "main.my": "from .lib import P\nfun main() {}\n",
        "lib.my": "pub struct P { x: Nope }\n",
    },
    "const_error_in_module": {
        "main.my": "from .lib import N\nfun main() {\n    print(N)\n}\n",
        "lib.my": "pub const N: int = 1 / 0\n",
    },
    "recursive_struct_in_module": {
        "main.my": "from .lib import P\nfun main() {}\n",
        "lib.my": "pub struct P { next: P }\n",
    },
    "trait_error_in_module": {
        "main.my": "from .lib import P\nfun main() {}\n",
        "lib.my": "pub struct P { x: int }\ntrait T {\n    fun f(self) -> int\n}\nimpl T for P {\n}\n",
    },
    "private_name": {
        "main.my": "from .lib import secret\nfun main() {\n    print(secret())\n}\n",
        "lib.my": "fun secret() -> int {\n    return 1\n}\n",
    },
    "unresolved": {"main.my": "fun f() {}\nimport nothere\nfun main() {}\n"},
    "module_as_value": {
        "main.my": "import lib\nfun main() {\n    let x = lib\n}\n",
        "lib.my": "pub fun f() -> int {\n    return 1\n}\n",
    },
    "nested_module_as_value": {
        "main.my": "import lib.inner\nfun main() {\n    let x = lib.inner\n}\n",
        "lib.my": "pub fun f() -> int {\n    return 1\n}\n",
        "lib/inner.my": "pub fun g() -> int {\n    return 2\n}\n",
    },
    "member_not_exported": {
        "main.my": "import lib\nfun main() {\n    print(lib.g())\n}\n",
        "lib.my": "fun g() -> int {\n    return 1\n}\n",
    },
    "import_collision": {
        "main.my": "from .lib import f\nfun f() -> int {\n    return 2\n}\nfun main() {}\n",
        "lib.my": "pub fun f() -> int {\n    return 1\n}\n",
    },
    "ambiguous_package": {
        "main.my": "import pkg\nfun main() {}\n",
        "pkg.my": "pub fun f() -> int {\n    return 1\n}\n",
        "pkg/pkg.my": "pub fun f() -> int {\n    return 2\n}\n",
    },
}

# A child's peak RSS counts its parent's memory at fork time, so the program
# is started from this minimal helper (a few MB) rather than from the test
# process, and the helper reports the program's exit code and peak (KB).
_MEASURE = (
    "import os, sys\n"
    "pid = os.posix_spawn(sys.argv[1], [sys.argv[1]], os.environ)\n"
    "_, status, usage = os.wait4(pid, 0)\n"
    "sys.stderr.write(f'{os.waitstatus_to_exitcode(status)} {usage.ru_maxrss}\\n')\n"
)


def _write_project(root: str, files: dict[str, str]) -> str:
    """Write a multi-module project under `root`; the path of its entry."""
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return os.path.join(root, "main.my")


def _corpus() -> list[str]:
    """Every single-file top-level example. The import-driven multi-file
    packages live in subdirectories and are filtered out by the glob."""
    files = glob.glob(os.path.join(_REPO, "examples", "*.my"))
    return sorted(f for f in files if os.path.basename(f) not in EXCLUDED)


def _oracle(path: str) -> tuple[str, int]:
    """(stdout, exit code) from the Python interpreter for `path`."""
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    out = io.StringIO()
    code = Interpreter(check(parse(tokenize(source))), out).run()
    return out.getvalue(), code


def _check_tool():
    return check(link(GEN_TOOL, stdlib_root=default_stdlib_root()))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class SelfHostedCodegenParity(unittest.TestCase):
    _binary: str | None = None
    _tmp: "tempfile.TemporaryDirectory | None" = None

    @classmethod
    def setUpClass(cls) -> None:
        from myla.compiler import build

        # Build the Myla compiler to a native binary when we can, so emitting
        # the assembly under test is a fast subprocess call. The Python x86
        # backend does not yet support every construct `codegen.my` uses, so
        # fall back to running the compiler source through the interpreter
        # rather than failing this gate on a *host*-backend gap. Once the host
        # backend catches up this path upgrades automatically.
        tmp = tempfile.TemporaryDirectory()
        binary = os.path.join(tmp.name, "gen_tool")
        try:
            build(_check_tool(), binary)
        except Exception:
            tmp.cleanup()
            return
        cls._tmp = tmp
        cls._binary = binary

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._tmp is not None:
            cls._tmp.cleanup()

    def _emit_asm(self, path: str, stdlib_root: str | None = None) -> str:
        """Assembly for `path`, produced by the self-hosted backend."""
        extra = [stdlib_root] if stdlib_root is not None else []
        if self._binary is not None:
            proc = subprocess.run(
                [self._binary, path, *extra], capture_output=True, text=True
            )
            self.assertEqual(
                proc.returncode, 0,
                f"self-hosted compile failed: {proc.stderr}",
            )
            return proc.stdout
        # Interpreter fallback (host backend can't build the compiler yet):
        # run the compiler source through the Python interpreter, with the
        # example path as argv[1] (what `gen_main` reads).
        out = io.StringIO()
        code = Interpreter(
            _check_tool(), out, argv=["gen_tool", path, *extra]
        ).run()
        self.assertEqual(code, 0, "self-hosted compile failed")
        return out.getvalue()

    def _build_and_run(self, asm: str) -> tuple[str, int]:
        """Assemble + link `asm` with the system toolchain, run it, return
        (stdout, exit code)."""
        out, code, _peak = self._build_and_measure(asm)
        return out, code

    def _build_and_measure(self, asm: str) -> tuple[str, int, float]:
        """Like `_build_and_run`, plus the program's peak memory in MB."""
        with tempfile.TemporaryDirectory() as tmp:
            asm_path = os.path.join(tmp, "out.s")
            obj_path = os.path.join(tmp, "out.o")
            bin_path = os.path.join(tmp, "out")
            with open(asm_path, "w", encoding="utf-8") as fh:
                fh.write(asm)
            subprocess.run(
                ["as", "--64", "-o", obj_path, asm_path], check=True,
                capture_output=True, text=True,
            )
            subprocess.run(
                ["ld", "-o", bin_path, obj_path], check=True,
                capture_output=True, text=True,
            )
            proc = subprocess.run(
                [sys.executable, "-I", "-S", "-c", _MEASURE, bin_path],
                capture_output=True, text=True,
            )
            code, peak_kb = proc.stderr.split()[-2:]
            return proc.stdout, int(code), int(peak_kb) / 1024

    def test_corpus_codegen_parity(self) -> None:
        checked = 0
        for path in _corpus():
            rel = os.path.relpath(path, _REPO)
            with self.subTest(file=rel):
                got = self._build_and_run(self._emit_asm(path))
                self.assertEqual(got, _oracle(path))
                checked += 1
        # Guard against the corpus silently going empty.
        self.assertGreater(checked, 20)

    def _linked_oracle(self, path: str) -> tuple[str, int]:
        out = io.StringIO()
        checker = check(link(path, stdlib_root=default_stdlib_root()))
        code = Interpreter(checker, out, argv=[path]).run()
        return out.getvalue(), code

    def test_module_programs_match_the_oracle(self) -> None:
        stdlib = default_stdlib_root()
        entries = {"examples/modules": os.path.join(_REPO, "examples", "modules", "main.my")}
        with tempfile.TemporaryDirectory() as tmp:
            for name, files in MODULE_PROJECTS.items():
                entries[name] = _write_project(os.path.join(tmp, name), files)
            for name, entry in entries.items():
                with self.subTest(program=name):
                    out, code = self._build_and_run(self._emit_asm(entry, stdlib))
                    expected, _ = self._linked_oracle(entry)
                    self.assertEqual((out, code), (expected, 0))

    def test_module_errors_match_the_python_loader(self) -> None:
        from myla.errors import MylaError

        if self._binary is None:
            self.skipTest("the self-hosted compiler could not be built natively")
        stdlib = default_stdlib_root()
        with tempfile.TemporaryDirectory() as tmp:
            for name, files in MODULE_ERRORS.items():
                with self.subTest(program=name):
                    entry = _write_project(os.path.join(tmp, name), files)
                    with self.assertRaises(MylaError) as ctx:
                        check(link(entry, stdlib_root=stdlib))
                    err = ctx.exception
                    path = err.path or entry
                    with open(path, encoding="utf-8") as fh:
                        expected = err.render(fh.read(), path)
                    proc = subprocess.run(
                        [self._binary, entry, stdlib], capture_output=True, text=True
                    )
                    self.assertEqual((proc.returncode, proc.stderr), (1, expected + "\n"))

    def test_stress_programs_reclaim_memory(self) -> None:
        from . import test_compiler_parity

        for name, expected in STRESS_PROGRAMS.items():
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, name.lower() + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(getattr(test_compiler_parity, name))
                out, code, peak = self._build_and_measure(self._emit_asm(path))
                self.assertEqual((out.strip(), code), (expected, 0))
                self.assertLess(peak, PEAK_LIMIT_MB, "memory was not reclaimed")

    def test_parity_programs_match_the_oracle(self) -> None:
        from .test_compiler_parity import PROGRAMS

        for name in PARITY_PROGRAMS:
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, name + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(PROGRAMS[name])
                got = self._build_and_run(self._emit_asm(path))
                self.assertEqual(got, _oracle(path))


if __name__ == "__main__":
    unittest.main()
