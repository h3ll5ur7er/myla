"""Differential burn test for the self-hosted code generator (self-hosting v0.9).

`selfhost/codegen.my` is the Myla-written x86-64 backend and
`selfhost/gen_main.my` the thin driver: it loads and links a program's modules,
type-checks it (with the same `Option`/`Result`/`get` prelude the Python `run`
injects), generates GAS assembly, and writes that assembly to
stdout. A host wrapper then runs `as`/`ld` over it to produce a real ELF binary
(see docs/Development/Testing.md).

This test closes the v0.9 *codegen* parity gate: for every runnable example in
the corpus, the binary produced by the self-hosted backend must have the same
(stdout, exit code) as the Python oracle (`myla run`, the tree-walking
interpreter).

How the assembly is produced. The self-hosted compiler is itself a Myla
program: `gen_main.my` is compiled once natively (cached by
`_tools.selfhost_tool`) and that binary is invoked per example, so the
*assembly under test* is emitted by the Myla-written backend.

The Python oracle's answers (its interpreter's output, its CLI's diagnostics)
are recorded (`tests/burn/_golden.py`, MYLA-219): the oracle functions below
run the retired Python toolchain only when recording. The comparisons with the
Python backend's binaries went with it.

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
import re
import subprocess
import sys
import tempfile
import unittest

from ._golden import golden
from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)

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
# char and float fields (MYLA-13), a match statement ending an arm block (MYLA-59),
# distinct names for generic instantiations (MYLA-9, MYLA-33), byte-range
# appends (MYLA-85), `?` on an operand larger than the result (MYLA-80).
PARITY_PROGRAMS = (
    "try_inside_push_leaves_the_list_intact",
    "try_inside_map_insert_leaves_the_map_intact",
    "try_inside_append_byte_leaves_the_builder_intact",
    "push_evaluates_its_value_before_the_list",
    "assign_replaces_map_and_builder_elements",
    "assign_heap_owning_struct_to_any_place",
    "assign_heap_owning_struct_to_itself",
    "method_arguments_survive_the_receivers_writes",
    "var_self_method_on_a_shared_element_copies_it",
    "heap_free_arguments_survive_the_receivers_writes",
    "borrowed_lets_survive_a_moved_value",
    "become_keeps_the_stack_flat",
    "become_passes_aggregates_by_value",
    "derived_eq_called_by_name",
    "strings_and_keys_around_eight_bytes",
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
    "match_statement_ending_an_arm_block",
    "generic_instantiations_get_distinct_names",
    "pop_a_boxed_enum",
    "remove_many_distinct_keys",
    "string_builder_append_range",
    "try_with_a_larger_success_payload",
    "derived_eq_on_plain_enums",
    "const_string_concatenation_in_functions",
    "local_closure_shadows_a_function",
    "local_closure_shadows_a_builtin",
    "plain_aggregates",
    "strings_through_the_ir",
    "lists_through_the_ir",
    "maps_and_builders_through_the_ir",
    "recursive_enums_through_the_ir",
    "try_through_the_ir",
    "function_values_through_the_ir",
    "logical_results_as_values",
    "aggregates_built_in_place",
    "format_renders_chars",
)

# The Python backend's arena-reclaim stress programs (test_compiler_parity),
# with their expected output. The self-hosted arena is 4 GiB, so rather than
# "doesn't run out", each program must also stay under PEAK_LIMIT_MB: they
# allocate and drop millions of cells, and without `free` they need 34 MB to
# over 4 GiB (with it, 8 to 18 MB) (MYLA-22).
STRESS_PROGRAMS = {
    "STRESS_SRC": "354000000",
    "STRESS_STR_OWNERSHIP_SRC": "4650000",
    "STRESS_TRY_SRC": "100000",
    "STRESS_TRY_AFTER_STAGED_VALUE_SRC": "7500000",
    "STRESS_TRY_IN_LITERAL_SRC": "1200000",
    "STRESS_LOOPCTL_SRC": "200001\n133333",
    "STRESS_LIST_SRC": "0",
    "STRESS_MAP_SRC": "0",
    "STRESS_MAP_REMOVE_SRC": "2399994",
    "STRESS_SB_SRC": "0",
    "STRESS_CLOSURE_SRC": "0",
    "STRESS_PARTIAL_SRC": "0",
    "STRESS_TRAIT_DISPATCH_SRC": "600000",
    "STRESS_FRAGMENTED_FREE_SRC": "38000",
    "STRESS_MATCH_RESULT_SRC": "120000000",
    "STRESS_MATCH_EARLY_EXIT_SRC": "270000000",
    "STRESS_CONDITION_TEMPS_SRC": "20100000",
    "STRESS_STR_SRC": "1800000",
    "STRESS_FOR_EARLY_RETURN_SRC": "6999999",
    "STRESS_LARGE_SIZES_SRC": "60002",
    "STRESS_MAP_OVERWRITE_SRC": "1090910",
    "STRESS_BOXED_MEMBERS_SRC": "3840000",
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
    # MYLA-105: the I/O intrinsics behind std.fs, std.process and std.io,
    # with results that don't depend on the machine
    "io_through_the_ir": {
        "main.my": (
            "from std.fs import read_to_string, write_to_file, current_dir, list_dir, make_dir, exists, is_dir, is_file\n"
            "from std.process import args, run\n"
            "from std.io import println, eprintln\n"
            "fun main() {\n"
            '    println("start")\n'
            '    eprintln("to stderr")\n'
            "    print(len(args()) > 0)\n"
            "    match current_dir() {\n"
            "        Ok(d) => { print(len(d) > 0) },\n"
            "        Err(e) => { print(false) },\n"
            "    }\n"
            '    match read_to_string("/nonexistent/file") {\n'
            "        Ok(s) => { print(s) },\n"
            '        Err(e) => { print("no file") },\n'
            "    }\n"
            '    match write_to_file("/nonexistent/dir/file", "x") {\n'
            "        Ok(n) => { print(n) },\n"
            '        Err(e) => { print("not written") },\n'
            "    }\n"
            '    match list_dir("/nonexistent") {\n'
            "        Ok(names) => { print(len(names)) },\n"
            '        Err(e) => { print("no dir") },\n'
            "    }\n"
            '    match make_dir("/nonexistent/a/b") {\n'
            "        Ok(n) => { print(n) },\n"
            '        Err(e) => { print("not made") },\n'
            "    }\n"
            '    print(exists("/"))\n'
            '    print(is_dir("/"))\n'
            '    print(is_file("/"))\n'
            '    match run("/bin/echo", ["hi"]) {\n'
            "        Ok(o) => { print(len(o.stdout)) },\n"
            '        Err(e) => { print("not run") },\n'
            "    }\n"
            "}\n"),
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
# diagnostic (message, file, position, source line and the carets underlining
# the error's range, MYLA-65).
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
    # an error at a module member: positioned at the module's name, the whole
    # member underlined (MYLA-65)
    "error_at_module_member": {
        "main.my": "import lib\nfun main() {\n    for x in lib.N {\n    }\n}\n",
        "lib.my": "pub const N: int = 1\n",
    },
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
    # several errors (MYLA-65, D80): each printed in its own file
    "parse_errors_in_module": {
        "main.my": "import lib\nfun main() {\n    print(lib.f())\n}\n",
        "lib.my": "pub fun f() -> int {\n    return 1 +\n}\npub fun g( {\n}\nfun h() {\n    let = 2\n}\n",
    },
    "type_errors_in_two_modules": {
        "main.my": "import lib\nfun main() {\n    let x: int = lib.f()\n    let y: str = 1\n}\n",
        "lib.my": "pub fun f() -> str {\n    return 1\n}\nfun g() {\n    print(nope)\n}\n",
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


# Diagnostics whose ranges are not plain one-line ASCII (MYLA-65).
DIAGNOSTICS = {
    "declaration_spanning_lines": "fun größe(n: int) -> int {\n    print(n)\n}\nfun main() {}\n",
    "characters_beyond_ascii": "fun main() {\n    let x = \"äö😀\" + 1\n}\n",
    "in_an_interpolation": "fun main() {\n    print(f\"é {nope(1)}!\")\n}\n",
    "unterminated_comment": "fun main() {}\n/* not\nclosed\n",
    "unterminated_string": "fun main() {\n    let s = \"ü\n}\n",
    "call_spanning_lines": "fun f(a: int, b: int) -> int {\n    return a\n}\nfun main() {\n    print(f(1,\n        \"x\"))\n}\n",
    "chain_starting_on_an_earlier_line": "struct P { x: int }\nfun main() {\n    let p = [P { x: 1 },\n        P { x: 2 }][0].nope()\n}\n",
    "newline_token": "fun main() {\n    let x = 1 +\n    print(x)\n}\n",
    "end_of_input": "fun main() {\n    let x = (1",
    # several errors (MYLA-65, D80), then the summary line
    "several_parse_errors": "fun main() {\n    let = 1\n    print(1 +)\n}\nfun g(a int) {}\nstruct S {\n    a: int b: int\n}\n",
    "several_type_errors": ("fun f() -> int {\n    return \"ä\"\n}\n#test(1)\nfun g(x: int) -> int {\n    return x\n}\n"
                            "fun main() {\n    let x: int = true\n}\n"),
    # notes (MYLA-65): on a later error, and in an imported module's file
    "notes_on_several_errors": ("fun f() {\n    let n = 1\n    n = 2\n}\n"
                                "fun main() {\n    let count = 1\n    print(cuont)\n}\n"),
    "note_in_an_imported_module": {
        "main.my": "from .util import label\nfun main() {\n    print(label(1))\n}\n",
        "util.my": "pub fun label(n: int) -> str {\n    return n * 2\n}\n",
    },
}


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


def _modules(entry: str) -> list[str]:
    """The files of the project whose entry is `entry` besides the entry, so
    that a recorded answer is keyed by every module of the program."""
    root = os.path.dirname(entry)
    files = glob.glob(os.path.join(root, "**", "*.my"), recursive=True)
    return sorted(f for f in files if f != entry)


@golden("selfhost_codegen.run")
def _oracle(path: str) -> tuple[str, int]:
    """(stdout, exit code) from the Python interpreter for `path`."""
    from myla.interpreter import Interpreter
    from myla.lexer import tokenize
    from myla.parser import parse
    from myla.types import check

    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    out = io.StringIO()
    code = Interpreter(check(parse(tokenize(source))), out).run()
    return out.getvalue(), code


@golden("selfhost_codegen.linked_run")
def _linked_oracle(path: str, modules: list[str]) -> tuple[str, int]:
    """(stdout, exit code) of the Python `link` + interpreter for the program
    whose entry is `path`; `modules` (its other files) only key the recorded
    answer."""
    from myla.interpreter import Interpreter
    from myla.loader import default_stdlib_root, link
    from myla.types import check

    out = io.StringIO()
    checker = check(link(path, stdlib_root=default_stdlib_root()))
    code = Interpreter(checker, out, argv=[path]).run()
    return out.getvalue(), code


@golden("selfhost_codegen.cli_run")
def _cli_oracle(entry: str) -> tuple[str, str, int]:
    """(stdout, stderr, exit code) of the Python `myla run` for `entry` (a
    single module): its output, then a runtime error rendered as the CLI
    prints it (as `test_selfhost_interp._cli_oracle`)."""
    from myla.errors import MylaError
    from myla.interpreter import Interpreter
    from myla.loader import default_stdlib_root, link
    from myla.types import check

    out = io.StringIO()
    try:
        code = Interpreter(check(link(entry, stdlib_root=default_stdlib_root())), out,
                           argv=[entry]).run()
        return out.getvalue(), "", code
    except MylaError as err:
        path = err.path or entry
        source = None
        if err.line is not None:
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
        return out.getvalue(), err.render(source, path) + "\n", 1


@golden("selfhost_codegen.runtime_error")
def _runtime_error_oracle(path: str) -> tuple[str, int, int] | None:
    """The Python interpreter's stdout and the line and column of the runtime
    error it stops `path` with (None if it doesn't)."""
    from myla.errors import MylaRuntimeError
    from myla.interpreter import Interpreter
    from myla.loader import default_stdlib_root, link
    from myla.types import check

    out = io.StringIO()
    try:
        Interpreter(check(link(path, stdlib_root=default_stdlib_root())), out).run()
    except MylaRuntimeError as err:
        return out.getvalue(), err.line, err.column
    return None


@golden("selfhost_codegen.diagnostic")
def _diagnostic_oracle(entry: str, modules: list[str]) -> str | None:
    """The Python CLI's diagnostic for `entry` (None if it accepts the
    program); `modules` (the program's other files) only key the recorded
    answer."""
    from myla.errors import MylaError
    from myla.loader import default_stdlib_root, link
    from myla.types import check

    try:
        check(link(entry, stdlib_root=default_stdlib_root()))
    except MylaError as err:
        # every error in its file, then a summary line (MYLA-65, D80)
        shown = []
        for e in (err, *err.more):
            path = e.path or entry
            with open(path, encoding="utf-8") as fh:
                shown.append(e.render(fh.read(), path))
        if err.more:
            shown.append(f"error: aborting due to {len(shown)} previous errors")
        return "\n\n".join(shown)
    return None


# A plain enum's derived `eq` (MYLA-87) and the reader of a function's
# instructions, as the Python backend's tests have them (tests/unit/
# test_compiler.py, which needs the retired toolchain).
PLAIN_ENUM_EQ = (
    "#derive(Eq)\nenum K { " + ", ".join(f"V{i}" for i in range(40)) + " }\n"
    "#derive(Eq)\nenum P { A(int), B }\n"
    "fun main() {\n    print(K.V3 == K.V39)\n    print(P.A(1) == P.B)\n}\n"
)


def function_body(asm: str, label: str) -> list[str]:
    """The instruction lines of the function at `label`, up to its `ret`
    (`ret $n` where the callee pops its arguments, MYLA-126)."""
    lines = asm.splitlines()
    start = lines.index(label + ":")
    body = []
    for line in lines[start + 1:]:
        line = line.strip()
        if not line or line.startswith("."):
            continue
        body.append(line)
        if line == "ret" or line.startswith("ret $"):
            return body
    raise AssertionError(f"no ret after {label}")


# MYLA-121: a loop, recursion keeping a value across a call, and a method
# reading `self` in a loop with a call inside
REGISTER_SAMPLE = (
    "fun sum_squares(n: int) -> int {\n"
    "    var total = 0\n"
    "    var i = 0\n"
    "    while i < n {\n"
    "        total = total + i * i\n"
    "        i = i + 1\n"
    "    }\n"
    "    return total\n"
    "}\n"
    "fun fib(n: int) -> int {\n"
    "    if n < 2 { return n }\n"
    "    return fib(n - 1) + fib(n - 2)\n"
    "}\n"
    "struct Acc { base: int, step: int }\n"
    "impl Acc {\n"
    "    fun run(self, n: int) -> int {\n"
    "        var s = self.base\n"
    "        var k = 0\n"
    "        while k < n {\n"
    "            s = s + self.step + fib(k % 3)\n"
    "            k = k + 1\n"
    "        }\n"
    "        return s\n"
    "    }\n"
    "}\n"
    "fun main() {\n"
    "    print(sum_squares(10))\n"
    "    print(fib(15))\n"
    "    let a = Acc { base: 100, step: 3 }\n"
    "    print(a.run(7))\n"
    "}\n")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class SelfHostedCodegenParity(unittest.TestCase):
    _binary: str

    @classmethod
    def setUpClass(cls) -> None:
        # The Myla compiler, built natively by the self-hosted compiler
        # (cached), so emitting the assembly under test is a fast subprocess
        # call.
        cls._binary = selfhost_tool("gen_main")

    def _emit_asm(self, path: str, stdlib_root: str | None = None, flags: tuple = ()) -> str:
        """Assembly for `path`, produced by the self-hosted backend."""
        extra = ([stdlib_root] if stdlib_root is not None else []) + list(flags)
        proc = subprocess.run(
            [self._binary, path, *extra], capture_output=True, text=True
        )
        self.assertEqual(
            proc.returncode, 0,
            f"self-hosted compile failed: {proc.stderr}",
        )
        return proc.stdout

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

    def test_derived_eq_on_a_plain_enum_compares_tags(self) -> None:
        # MYLA-87: a few instructions, however many variants
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "eq.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(PLAIN_ENUM_EQ)
            asm = self._emit_asm(path)
        body = function_body(asm, "myla_K.eq")
        self.assertLess(len(body), 15, "\n".join(body))
        self.assertGreater(len(function_body(asm, "myla_P.eq")), 15)

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

    def test_runtime_errors_match_the_python_backend(self) -> None:
        # Every runtime error of the error corpus: stderr `runtime error:
        # <message>` and `  --> file:line:col`, at the interpreter's position,
        # exit status 1 (MYLA-65, MYLA-66), after what the interpreter printed.
        # (It also compared stdout and stderr with the Python backend's
        # binary, retired with it, MYLA-219.)
        runtime = sorted(glob.glob(os.path.join(_REPO, "examples", "errors", "runtime_*.my")))
        self.assertGreater(len(runtime), 8)
        for path in runtime:
            with self.subTest(file=os.path.basename(path)), tempfile.TemporaryDirectory() as tmp:
                interp = _runtime_error_oracle(path)
                self.assertIsNotNone(interp, "the interpreter ran it without a runtime error")
                want_out, line, column = interp
                asm = os.path.join(tmp, "self.s")
                with open(asm, "w", encoding="utf-8") as fh:
                    fh.write(self._emit_asm(path))
                subprocess.run(["as", "--64", "-o", asm + ".o", asm], check=True)
                subprocess.run(["ld", "-o", asm + ".bin", asm + ".o"], check=True)
                sh = subprocess.run([asm + ".bin"], capture_output=True, text=True)
                self.assertEqual((sh.stdout, sh.returncode), (want_out, 1))
                self.assertTrue(sh.stderr.startswith("runtime error: "), sh.stderr)
                self.assertTrue(sh.stderr.endswith(f"\n  --> {path}:{line}:{column}\n"),
                                sh.stderr)

    def test_module_programs_match_the_oracle(self) -> None:
        stdlib = STDLIB_ROOT
        entries = {"examples/modules": os.path.join(_REPO, "examples", "modules", "main.my")}
        with tempfile.TemporaryDirectory() as tmp:
            for name, files in MODULE_PROJECTS.items():
                entries[name] = _write_project(os.path.join(tmp, name), files)
            for name, entry in entries.items():
                with self.subTest(program=name):
                    out, code = self._build_and_run(self._emit_asm(entry, stdlib))
                    expected, _ = _linked_oracle(entry, _modules(entry))
                    self.assertEqual((out, code), (expected, 0))

    def _assert_diagnostic_matches(self, entry: str, stdlib: str, modules: list[str]) -> None:
        """The self-hosted compiler rejects `entry` with exactly the Python
        CLI's diagnostic, carets included; `modules` are the program's other
        files."""
        expected = _diagnostic_oracle(entry, modules)
        self.assertIsNotNone(expected, "the Python toolchain accepted the program")
        proc = subprocess.run(
            [self._binary, entry, stdlib], capture_output=True, text=True
        )
        self.assertEqual((proc.returncode, proc.stderr), (1, expected + "\n"))

    def test_module_errors_match_the_python_loader(self) -> None:
        stdlib = STDLIB_ROOT
        with tempfile.TemporaryDirectory() as tmp:
            for name, files in MODULE_ERRORS.items():
                with self.subTest(program=name):
                    entry = _write_project(os.path.join(tmp, name), files)
                    self._assert_diagnostic_matches(entry, stdlib, _modules(entry))

    def test_diagnostics_match_the_python_cli(self) -> None:
        # every lex, parse, module and type error of the corpus, and ranges
        # that run past their line, hold other characters or sit in an
        # f-string: the same text, the same carets (MYLA-65)
        stdlib = STDLIB_ROOT
        cases = {os.path.basename(p): p for p in glob.glob(os.path.join(_REPO, "examples", "errors", "*.my"))
                 if not os.path.basename(p).startswith("runtime_")}
        self.assertGreater(len(cases), 100)
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in DIAGNOSTICS.items():
                files = source if isinstance(source, dict) else {"main.my": source}
                cases[name] = _write_project(os.path.join(tmp, name), files)
            for name, entry in sorted(cases.items()):
                with self.subTest(case=name):
                    # the examples are single files; each case of DIAGNOSTICS
                    # has a directory of its own
                    modules = _modules(entry) if name in DIAGNOSTICS else []
                    self._assert_diagnostic_matches(entry, stdlib, modules)

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

    def test_the_ir_text_form(self) -> None:
        # every function goes through the IR (D79, MYLA-107); `--emit-ir`
        # prints it
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(IR_SAMPLE)
            proc = subprocess.run([self._binary, path, "--emit-ir"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        start = proc.stdout.index("fun myla_scale")
        self.assertEqual(proc.stdout[start:proc.stdout.index("}\n", start) + 2], IR_SAMPLE_TEXT)

    def test_lets_of_fixed_variables_borrow(self) -> None:
        # MYLA-122: a `let` of a part of a variable nothing writes while it
        # lives (a parameter, a `let`, a loop's element), and a `for` over
        # one, take no reference of their own; a `var`, or a `let` of one,
        # still does
        source = (
            "struct P { name: str, tags: [str] }\n"
            "fun borrowing(p: P) -> int {\n"
            "    let n = p.name\n"
            "    let t = p.tags\n"
            "    let first = t[0]\n"
            "    var total = len(n) + len(first)\n"
            "    for x in t {\n"
            "        let y = x\n"
            "        total = total + len(y)\n"
            "    }\n"
            "    return total\n"
            "}\n"
            "fun owning(p: P) -> int {\n"
            "    var q = p\n"
            "    let n = q.name\n"
            "    q.name = \"z\"\n"
            "    return len(n)\n"
            "}\n"
            "fun main() {\n"
            "    let p = P { name: \"ab\", tags: [\"x\", \"yz\"] }\n"
            "    print(borrowing(p))\n"
            "    print(owning(p))\n"
            "}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            self.assertEqual(self._build_and_run(self._emit_asm(path)), ("6\n2\n", 0))
            proc = subprocess.run([self._binary, path, "--emit-ir"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

        def ir_of(name: str) -> str:
            start = proc.stdout.index(f"fun myla_{name} ")
            return proc.stdout[start:proc.stdout.index("}\n", start)]

        borrowing = ir_of("borrowing")
        self.assertNotIn("retain", borrowing, borrowing)
        self.assertNotIn("drop", borrowing, borrowing)
        owning = ir_of("owning")
        self.assertIn(" q: P (16 bytes) owns\n", owning)
        self.assertIn(" n: str owns\n", owning)

    def test_a_last_use_moves(self) -> None:
        # MYLA-127: a value taken from an owning variable that nothing reads
        # afterwards moves (no retain, and no drop of the variable); one read
        # again, or read through after it is taken, is retained
        source = (
            "struct Box2 { name: str, tags: [str] }\n"
            "fun make_list(n: int) -> [int] {\n"
            "    var out: [int] = []\n"
            "    for i in 0..n { push(out, i) }\n"
            "    return out\n"
            "}\n"
            "fun boxed(s: str) -> Box2 {\n"
            "    var b = Box2 { name: s + \"!\", tags: [] }\n"
            "    push(b.tags, s)\n"
            "    return b\n"
            "}\n"
            "fun again(s: str) -> [str] {\n"
            "    var t = s + \"?\"\n"
            "    var xs: [str] = []\n"
            "    push(xs, t)\n"
            "    print(t)\n"
            "    return xs\n"
            "}\n"
            "fun main() {\n"
            "    print(len(make_list(5)))\n"
            "    let b = boxed(\"x\")\n"
            "    print(b.name)\n"
            "    print(len(b.tags))\n"
            "    print(len(again(\"y\")))\n"
            "}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            self.assertEqual(self._build_and_run(self._emit_asm(path)), ("5\nx!\n1\ny?\n1\n", 0))
            proc = subprocess.run([self._binary, path, "--emit-ir"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

        def ir_of(name: str) -> str:
            start = proc.stdout.index(f"fun myla_{name} ")
            return proc.stdout[start:proc.stdout.index("}\n", start)]

        made = ir_of("make_list")
        self.assertNotIn("retain", made, made)
        self.assertIn("moved $1\n", made, made)
        boxed = ir_of("boxed")
        self.assertNotIn("retain Box2", boxed, boxed)
        # `t` is printed after it is pushed: retained for the list
        self.assertIn("retain str", ir_of("again"))

    def test_only_reachable_functions_are_emitted(self) -> None:
        # MYLA-108: from the entry point, through calls, function values and
        # partial applications
        source = (
            "fun unused() -> int { return 1 }\n"
            "fun called() -> int { return 2 }\n"
            "fun as_value(x: int) -> int { return x }\n"
            "fun partly(a: int, b: int) -> int { return a + b }\n"
            "fun main() {\n"
            "    let f = as_value\n"
            "    let g = partly(1, _)\n"
            "    print(called() + f(3) + g(4))\n"
            "}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), ("10\n", 0))
        self.assertNotIn("myla_unused:", asm)
        for name in ("called", "as_value", "partly", "main"):
            self.assertIn(f"myla_{name}:", asm)

    def _function_asm(self, asm: str, name: str) -> str:
        """The lines of `myla_<name>`, up to its `ret`."""
        lines = asm.split("\n")
        start = lines.index(f"myla_{name}:")
        end = next(i for i in range(start, len(lines)) if lines[i].strip().split(" ")[0] == "ret")
        return "\n".join(lines[start:end + 1])

    def test_a_comparison_feeding_a_branch_is_a_conditional_jump(self) -> None:
        # MYLA-120: no bool is made for an integer comparison whose only use
        # is the branch after it; each condition and operand kind still works
        source = (
            "fun pick(a: int, b: int, c: uint8, d: char, e: bool) -> int {\n"
            "    var n = 0\n"
            "    if a < b { n = n + 1 }\n"
            "    if a >= b { n = n + 2 }\n"
            "    if c > 200u8 { n = n + 4 }\n"
            "    if d == 'x' { n = n + 8 }\n"
            "    if e != true { n = n + 16 }\n"
            "    var i = 0\n"
            "    while i <= b {\n"
            "        i = i + 1\n"
            "    }\n"
            "    let keep = a > b\n"
            "    if keep { n = n + 32 }\n"
            "    return n + i\n"
            "}\n"
            "fun main() {\n"
            "    print(pick(1, 2, 250u8, 'x', false))\n"
            "    print(pick(-3, -5, 7u8, 'y', true))\n"
            "}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), ("32\n34\n", 0))
        body = self._function_asm(asm, "pick")
        # only `let keep = a > b` makes a bool
        self.assertEqual(body.count("\tset"), 1, body)
        self.assertNotIn("movzbq %al", body.replace("setg %al\n\tmovzbq %al", ""), body)

    def test_scalars_live_in_callee_saved_registers(self) -> None:
        # MYLA-121: a loop's variables, a value kept across a call and a
        # parameter read in a loop live in %rbx and %r12-%r15, which each
        # function saves before writing and restores before returning
        source = REGISTER_SAMPLE
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), ("285\n610\n125\n", 0))
        saved = r"%(rbx|r12|r13|r14|r15)"
        scratch = r"%(r8|r9|r10|r11)"
        # the frame is touched only to save and restore those registers and
        # to read the parameters into them; a value no call or runtime helper
        # comes between the uses of lives in %r8-%r11, which need no save
        # (MYLA-134)
        for name in ("sum_squares", "Acc.run"):
            body = self._function_asm(asm, name)
            frame = [l.strip() for l in body.split("\n") if "(%rbp)" in l]
            for line in frame:
                self.assertRegex(line, rf"^movq ({saved}, -\d+\(%rbp\)|-?\d+\(%rbp\), ({saved}|{scratch}))$", body)
            self.assertTrue(frame, body)
        squares = self._function_asm(asm, "sum_squares")
        self.assertRegex(squares, scratch)
        self.assertNotRegex(squares, rf"movq {saved}, -\d+\(%rbp\)")
        # the loop of `Acc.run` calls `fib`: what lives across it stays in
        # the callee-saved registers
        self.assertRegex(self._function_asm(asm, "Acc.run"), rf"movq {saved}, -\d+\(%rbp\)")
        self.assertEqual(self._unsaved_callee_saved(asm), [])

    def test_division_by_a_constant_tests_nothing(self) -> None:
        # MYLA-125: a divisor known not to be 0 or -1 needs neither test; an
        # unsigned power of two is a shift or a mask
        source = (
            "fun f(x: int, y: uint32, z: int64) -> int64 {\n"
            "    let a = x / 7 + x % 7\n"
            "    let b = y / 8u32 + y % 8u32\n"
            "    let c = z / -3 + z % 1000000\n"
            "    return (a as int64) + (b as int64) + c\n"
            "}\n"
            "fun g(x: int, n: int) -> int { return x / n + x % -1 }\n"
            "fun main() {\n"
            "    print(f(-100, 4000000003u32, -9876543210))\n"
            "    print(g(-2147483648, -1))\n"
            "}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            expected = _oracle(path)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), expected)
        body = self._function_asm(asm, "f")
        self.assertNotIn("testq %rcx, %rcx", body, body)
        self.assertNotIn("cmpq $-1, %rcx", body, body)
        self.assertNotIn("divq", body.replace("idivq", ""), body)   # unsigned by 8: shift and mask
        # a divisor that may be 0 or -1 keeps both tests
        g = self._function_asm(asm, "g")
        self.assertIn("testq %rcx, %rcx", g, g)

    def test_loads_go_straight_into_registers(self) -> None:
        # MYLA-125: a value loaded for a temporary or variable in a register
        # isn't loaded into %rax first and moved
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(REGISTER_SAMPLE)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), ("285\n610\n125\n", 0))
        # in the compiled functions (the runtime is written by hand)
        lines, routine = [], ""
        for line in asm.split("\n"):
            if re.match(r"^[A-Za-z_][\w$.]*:", line):
                routine = line
            elif routine.startswith("myla_"):
                lines.append(line.strip())
        pairs = [(a, b) for a, b in zip(lines, lines[1:])
                 if re.fullmatch(r"(movq|leaq) (.*), %rax", a)
                 and not re.search(r"%(r|e)?ax\b|%al\b", a.rsplit(",", 1)[0])
                 and re.fullmatch(r"movq %rax, %(rbx|r12|r13|r14|r15)", b)]
        self.assertEqual(pairs, [])

    def test_calls_in_tail_position_reuse_the_frame(self) -> None:
        # MYLA-126: a call whose result is returned at once jumps, so deep
        # recursion runs in constant stack (ten million frames would overflow
        # it), also between functions taking more or fewer arguments; a call
        # passing an address in the caller's frame, or followed by a drop,
        # stays a call
        source = (
            "struct P { a: int, b: int }\n"
            "fun count_down(n: int, acc: int64) -> int64 {\n"
            "    if n == 0 { return acc }\n"
            "    return count_down(n - 1, acc + (n as int64))\n"
            "}\n"
            "fun is_even(n: int) -> bool {\n"
            "    if n == 0 { return true }\n"
            "    return is_odd(n - 1)\n"
            "}\n"
            "fun is_odd(n: int) -> bool {\n"
            "    if n == 0 { return false }\n"
            "    return is_even(n - 1)\n"
            "}\n"
            "fun spread(n: int) -> int64 {\n"
            "    if n == 0 { return 0 }\n"
            "    return gather(n - 1, n, 2)\n"
            "}\n"
            "fun gather(n: int, a: int, b: int) -> int64 {\n"
            "    if n == 0 { return (a + b) as int64 }\n"
            "    return spread(n - 1)\n"
            "}\n"
            "fun sum(p: P) -> int { return p.a + p.b }\n"
            "fun via_local(x: int) -> int {\n"
            "    let p = P { a: x, b: 2 }\n"
            "    return sum(p)\n"
            "}\n"
            "fun label(n: int, s: str) -> str {\n"
            "    if n == 0 { return s }\n"
            "    let t = s + \"x\"\n"
            "    return label(n - 1, t)\n"
            "}\n"
            "fun main() {\n"
            "    print(count_down(10000000, 0))\n"
            "    print(is_even(1000001))\n"
            "    print(spread(10000001))\n"
            "    print(via_local(40))\n"
            "    print(label(3, \"a\"))\n"
            "    let f = count_down\n"
            "    print(f(10, 0))\n"
            "    let g = ((x: int) => x + 1) >> ((y: int) => y * 2)\n"
            "    print(g(3))\n"
            "}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), ("50000005000000\nfalse\n3\n42\naxxx\n55\n8\n", 0))
        self.assertIn("jmp myla_count_down", self._function_asm(asm, "count_down"))
        self.assertIn("jmp myla_is_odd", self._function_asm(asm, "is_even"))
        self.assertIn("call myla_sum", self._function_asm(asm, "via_local"))
        self.assertIn("call myla_label", self._function_asm(asm, "label"))

    def test_tail_calls_hand_over_owned_arguments(self) -> None:
        # MYLA-127, MYLA-126: a parameter passed owned lets a call in tail
        # position take a value the caller owns, and the caller's other owners
        # are dropped before the jump, so a recursion threading a list runs in
        # constant stack (and the list isn't copied); an argument borrowed from
        # an owner dropped after the call keeps the call
        source = (
            "fun collect(n: int, acc: [int]) -> [int] {\n"
            "    if n == 0 { return acc }\n"
            "    var next = acc\n"
            "    push(next, n)\n"
            "    return collect(n - 1, next)\n"
            "}\n"
            "fun label(n: int, s: str) -> str {\n"
            "    if n == 0 { return s }\n"
            "    let t = s + \"x\"\n"
            "    return label(n - 1, t)\n"
            "}\n"
            "fun first_of(xs: [str]) -> str { return xs[0] }\n"
            "fun maybe(n: int) -> Option<[str]> {\n"
            "    if n > 0 { return Some([\"m\" + \"n\"]) }\n"
            "    return None\n"
            "}\n"
            "fun through_match(n: int) -> str {\n"
            "    match maybe(n) {\n"
            "        Some(rest) => { return first_of(rest) },\n"
            "        None => {},\n"
            "    }\n"
            "    return \"\"\n"
            "}\n"
            "fun borrowed(n: int) -> str {\n"
            "    let t = [\"a\" + \"b\"]\n"
            "    return first_of(t)\n"
            "}\n"
            "fun main() {\n"
            "    let xs = collect(1000000, [])\n"
            "    print(len(xs))\n"
            "    print(xs[999999])\n"
            "    print(label(3, \"q\" + \"r\"))\n"
            "    print(borrowed(1))\n"
            "    print(through_match(1))\n"
            "}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), ("1000000\n1\nqrxxx\nab\nmn\n", 0))
        self.assertIn("jmp myla_collect", self._function_asm(asm, "collect"))
        self.assertIn("jmp myla_label", self._function_asm(asm, "label"))
        self.assertIn("call myla_first_of", self._function_asm(asm, "borrowed"))
        # `rest` borrows from the match's value, dropped after the call
        self.assertIn("call myla_first_of", self._function_asm(asm, "through_match"))

    def test_become_replaces_the_frame(self) -> None:
        # MYLA-128, D87: every `become` of the parity program jumps, so it runs
        # a million calls deep in the default stack (a `return` of the same
        # calls overflows it), and so it does built with -g
        from .test_compiler_parity import PROGRAMS
        source = (PROGRAMS["become_keeps_the_stack_flat"]
                  .replace("let deep = 20000", "let deep = 1000000")
                  .replace("0..1000 {", "0..1000000 {"))
        expected = ("1784293664\ntrue\ntrue\n3000000\n3000000\n2000000\n459109\n3\n"
                    "1000001\n1000000\n2999997\n2999997\n1000\nc\nabc\n42\n789\ndone\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), (expected, 0))
            proc = subprocess.run([self._binary, path, "-g"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(self._build_and_run(proc.stdout), (expected, 0))
            ir = subprocess.run([self._binary, path, "--emit-ir"], capture_output=True, text=True).stdout
        self.assertIn("jmp myla_count", self._function_asm(asm, "count"))
        self.assertIn("jmp myla_Counter.run", self._function_asm(asm, "Counter.run"))
        self.assertIn("jmp myla_Walker.walk", self._function_asm(asm, "Walker.walk"))
        self.assertIn("jmp myla_fib", self._function_asm(asm, "fib"))
        self.assertIn("jmp myla_label", self._function_asm(asm, "label"))
        self.assertIn("jmp *%rcx", self._function_asm(asm, "spin"))
        self.assertIn("jmp *%rcx", self._function_asm(asm, "via"))
        # the IR's text form: the call, then the terminator
        self.assertRegex(ir, r"call myla_count\(%t\d+, %t\d+\)\n  become\n")
        # MYLA-130: the list `total` passes on is handed over (read before
        # its drop, not retained), and a word already in place stays there
        total_ir = ir[ir.index("fun myla_total"):]
        total_ir = total_ir[:total_ir.index("\n}")]
        self.assertNotIn("retain", total_ir)
        self.assertIn("moved $0", total_ir)
        self.assertNotIn("popq 16(%rbp)", self._function_asm(asm, "fib"))

    def test_become_passes_aggregates_by_value(self) -> None:
        # MYLA-131, D88: the parity program a million deep, with and without
        # -g; the parameters a `become` hands an aggregate over to hold it in
        # their argument words; each step's copy is released (kept, the
        # strings would take more than 1 GiB)
        from .test_compiler_parity import PROGRAMS
        source = PROGRAMS["become_passes_aggregates_by_value"].replace("let deep = 20000", "let deep = 1000000")
        expected = ("counted 1000000\n3000000\nrs\n2\n1001\n1000\n3000000\n5\ntext!\n"
                    "1000004\n11\n10\n13\nk\n")
        leak = (
            "struct Named { name: str, steps: [int] }\n"
            "fun rename(t: Named, n: int) -> Named {\n"
            "    if n == 0 { return t }\n"
            "    become rename(Named { name: t.name + \"x\", steps: t.steps }, n - 1)\n"
            "}\n"
            "fun main() {\n"
            "    print(len(rename(Named { name: \"\", steps: [1] }, 50000).name))\n"
            "}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), (expected, 0))
            proc = subprocess.run([self._binary, path, "-g"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(self._build_and_run(proc.stdout), (expected, 0))
            ir = subprocess.run([self._binary, path, "--emit-ir"], capture_output=True, text=True).stdout
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(leak)
            out, code, peak = self._build_and_measure(self._emit_asm(path))
        self.assertEqual((out, code), ("50000\n", 0))
        self.assertLess(peak, 64)
        self.assertIn("jmp myla_walk", self._function_asm(asm, "walk"))
        self.assertRegex(ir, r"\$\d+ p: Pos \(argument 1, 16 bytes by value\)\n")
        self.assertRegex(ir, r"\$\d+ s: State \(argument 0, 16 bytes by value\) owns\n")

    def test_payload_free_enums_compare_tags(self) -> None:
        # MYLA-133: `==` on an enum without payloads whose `eq` is derived is
        # a compare of the tags, no call
        source = (
            "#derive(Eq)\nenum Light { Red, Green }\n"
            "#derive(Eq)\nenum Shape { Dot, Box(int) }\n"
            "fun red(l: Light) -> bool {\n    return l == Light.Red\n}\n"
            "fun dot(s: Shape) -> bool {\n    return s == Shape.Dot\n}\n"
            "fun main() {\n"
            "    print(red(Light.Red))\n    print(red(Light.Green))\n"
            "    print(dot(Shape.Dot))\n    print(dot(Shape.Box(1)))\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), ("true\nfalse\ntrue\nfalse\n", 0))
        self.assertNotIn("call myla_Light.eq", self._function_asm(asm, "red"))
        self.assertIn("call myla_Shape.eq", self._function_asm(asm, "dot"))

    def test_partial_application_thunks_jump(self) -> None:
        # MYLA-130: a partial application's thunk jumps to its function (or
        # through its function value), so a `become` through one runs in
        # constant stack too
        source = (
            "struct Machine { step: int, next: (Machine, int, int) -> int }\n"
            "struct Big { a: int, b: int, c: int }\n"
            "fun hop(k: int, m: Machine, n: int, acc: int) -> int {\n"
            "    if n == 0 { return acc }\n"
            "    become m.next(m, n - 1, acc + k)\n"
            "}\n"
            "fun weigh(big: Big, s: str, x: int) -> Big {\n"
            "    return Big { a: big.a + x, b: len(s), c: big.c }\n"
            "}\n"
            "fun main() {\n"
            "    let m = Machine { step: 0, next: hop(3, _, _, _) }\n"
            "    print(m.next(m, 1000000, 0))\n"
            "    let w = weigh(Big { a: 1, b: 2, c: 3 }, \"ab\" + \"c\", _)\n"
            "    let r = w(4)\n"
            "    print(r.a + r.b + r.c)\n"
            "    let f = (a: int, b: int) => a * b\n"
            "    let g = f(_, 7)\n"
            "    print(g(6))\n"
            "}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            asm = self._emit_asm(path)
            self.assertEqual(self._build_and_run(asm), ("3000000\n11\n42\n", 0))
        thunks = [line for line in asm.split("\n") if line.startswith("\tjmp myla_hop") or line == "\tjmp *%rcx"]
        self.assertGreaterEqual(len(thunks), 2)
        self.assertNotIn("call myla_hop", asm)

    def _unsaved_callee_saved(self, asm: str) -> list:
        """The routines of `asm` writing %rbx or %r12-%r15 without saving it
        first (a push, or a store into the frame)."""
        names = {"rbx": ("%rbx", "%ebx", "%bx", "%bl")}
        for r in ("r12", "r13", "r14", "r15"):
            names[r] = tuple(f"%{r}{suffix}" for suffix in ("", "d", "w", "b"))
        bad, fn, kept = set(), None, set()
        for line in asm.split("\n"):
            if re.match(r"^[A-Za-z_][\w$.]*:", line):
                fn, kept = line.split(":")[0], set()
                continue
            s = line.strip()
            m = re.match(r"(?:pushq %(\w+)|movq %(\w+), -?\d+\(%rbp\))$", s)
            if m:
                kept.add(m.group(1) or m.group(2))
                continue
            if s.startswith(("popq", "push", "cmp", "test", "call", "j")):
                continue
            parts = s.split(None, 1)
            if len(parts) < 2:
                continue
            dest = parts[1].rsplit(",", 1)[-1].strip()
            for r, forms in names.items():
                if dest in forms and r not in kept:
                    bad.add((fn, r))
        return sorted(bad)

    def test_concurrency_programs_match_the_interpreter(self) -> None:
        """Every concurrency parity program (D89) and the actor programs,
        natively (D90, D91: tasks taking turns on one thread), print and exit
        as the Python interpreter does; a program without `async let` also
        with its async functions on frames (`--async-frames`)."""
        from .test_selfhost_interp import CONCURRENCY_PROGRAMS

        cases = dict(ACTOR_PROGRAMS)
        cases.update(CONCURRENCY_PROGRAMS)
        stdlib = STDLIB_ROOT
        for name, src in cases.items():
            modes = [()] if "async let" in src or "task." in src else [(), ("--async-frames",)]
            for flags in modes:
                with self.subTest(program=name, flags=flags), tempfile.TemporaryDirectory() as tmp:
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(src)
                    out, code, peak = self._build_and_measure(self._emit_asm(path, stdlib, flags))
                    want = _cli_oracle(path)
                    self.assertEqual((out, code), (want[0], want[2]))
                    # 200,000 actors made and released: their cells are reused
                    self.assertLess(peak, 64, f"{name}: peak {peak:.1f} MB")

    def test_deep_task_trees_and_awaits(self) -> None:
        """3,000 children through `task.all`, each calling an actor, and an
        async recursion 100,000 deep: every await is a tail call, so the
        stack stays flat, and the frames are freed as they end."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "deep.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(DEEP_TASKS)
            out, code, peak = self._build_and_measure(self._emit_asm(path, STDLIB_ROOT))
            self.assertEqual((out, code), ("8997000\n3000\n100000\n", 0))
            self.assertLess(peak, 64, f"peak {peak:.1f} MB")

    def test_child_failures_end_the_program_at_once(self) -> None:
        """A panic or `exit` in a child task ends the program at once: every
        other task stops at its next suspension point, then the failure is
        reported (D97; it used to wait for the parent's `await` or scope end,
        D89). On one thread the order is fixed: the self-hosted interpreter
        prints the same; the Python interpreter's threads may interleave."""
        stdlib = STDLIB_ROOT
        for name, (src, want_out, want_code, want_err) in CHILD_FAILURES.items():
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, name + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(src)
                exe = os.path.join(tmp, name)
                with open(exe + ".s", "w", encoding="utf-8") as fh:
                    fh.write(self._emit_asm(path, stdlib))
                subprocess.run(["gcc", "-nostdlib", "-static", "-o", exe, exe + ".s"], check=True)
                # one worker: the order the self-hosted interpreter has (D92)
                env = dict(os.environ, MYLA_THREADS="1")
                proc = subprocess.run([exe], capture_output=True, text=True, timeout=60, env=env)
                self.assertEqual((proc.stdout, proc.returncode), (want_out, want_code))
                self.assertTrue(proc.stderr.startswith(want_err), proc.stderr)

    def test_tasks_on_any_number_of_workers(self) -> None:
        """The concurrency programs with child tasks print and exit alike on
        1 to 16 workers (D92), run several times each: tasks on other threads,
        actors entered from several at once, cells freed on another worker's
        heap, values copied deeply as they cross."""
        from .test_selfhost_interp import CONCURRENCY_PROGRAMS

        cases = {n: s for n, s in CONCURRENCY_PROGRAMS.items() if "async let" in s or "task." in s}
        cases["values_cross_deeply"] = ACTOR_PROGRAMS["values_cross_deeply"]
        cases["deep_task_trees"] = DEEP_TASKS
        cases["task_tree"] = TASK_TREE
        stdlib = STDLIB_ROOT
        for name, src in cases.items():
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, name + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(src)
                exe = os.path.join(tmp, name)
                with open(exe + ".s", "w", encoding="utf-8") as fh:
                    fh.write(self._emit_asm(path, stdlib))
                subprocess.run(["gcc", "-nostdlib", "-static", "-o", exe, exe + ".s"], check=True)
                want = None
                for workers in ["1", "2", "4", "8", "16"]:
                    for _ in range(4):
                        env = dict(os.environ, MYLA_THREADS=workers)
                        proc = subprocess.run([exe], capture_output=True, text=True, timeout=60, env=env)
                        got = (proc.stdout, proc.returncode)
                        if want is None:
                            want = got
                        self.assertEqual(got, want, f"{workers} workers")

    def test_children_run_in_parallel(self) -> None:
        """Eight CPU-bound children on as many workers as CPUs: the process
        uses well over one CPU's time per second of wall time (D89 (3))."""
        if (os.cpu_count() or 1) < 2:
            self.skipTest("one CPU")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "par.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(PARALLEL_WORK)
            exe = os.path.join(tmp, "par")
            with open(exe + ".s", "w", encoding="utf-8") as fh:
                fh.write(self._emit_asm(path, STDLIB_ROOT))
            subprocess.run(["gcc", "-nostdlib", "-static", "-o", exe, exe + ".s"], check=True)
            env = dict(os.environ)
            env.pop("MYLA_THREADS", None)
            proc = subprocess.run(
                [sys.executable, "-I", "-S", "-c", _CPU_AND_WALL, exe],
                capture_output=True, text=True, env=env,
            )
            out, cpu, wall = proc.stdout, *map(float, proc.stderr.split()[-2:])
            self.assertEqual(out, "1\n")
            self.assertGreater(cpu, 1.5 * wall, f"cpu {cpu:.2f} s, wall {wall:.2f} s")

    def test_parity_programs_match_the_oracle(self) -> None:
        from .test_compiler_parity import PROGRAMS

        for name in PARITY_PROGRAMS:
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, name + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(PROGRAMS[name])
                got = self._build_and_run(self._emit_asm(path))
                self.assertEqual(got, _oracle(path))



# Actors and concurrency natively (D89, D91, MYLA-138): one task so far, so
# async functions are ordinary ones; an actor is a handle to a cell holding its
# fields, shared by its copies and released with the last.
_ACTOR_COUNTER = ("actor Counter {\n    count: int,\n    log: [str],\n}\n"
                  "impl Counter {\n"
                  "    fun bump(var self, by: int) -> int {\n        self.count = self.count + by\n"
                  "        push(self.log, f\"+{by}\")\n        return self.count\n    }\n"
                  "    fun get(self) -> int {\n        return self.count\n    }\n"
                  "    fun entries(self) -> [str] {\n        return self.log\n    }\n}\n")
ACTOR_PROGRAMS = {
    "actor_handles_are_shared": _ACTOR_COUNTER + (
        "struct Holder { c: Counter, tag: str }\n"
        "async fun bump_all(cs: [Counter]) {\n    for c in cs {\n        let x = await c.bump(10)\n    }\n}\n"
        "#main\nasync fun main() {\n    let c = Counter { count: 0, log: [] }\n    let d = c\n"
        "    let h = Holder { c: d, tag: \"h\" }\n    let x = await h.c.bump(1)\n"
        "    await bump_all([c, d, h.c])\n    print(await c.get())\n"
        "    var es = await c.entries()\n    push(es, \"local\")\n    print(len(es))\n"
        "    print(len(await d.entries()))\n}\n"),
    "actors_are_released": _ACTOR_COUNTER + (
        "async fun churn(n: int) -> int {\n    var total = 0\n    var i = 0\n    while i < n {\n"
        "        let c = Counter { count: i, log: [\"start\"] }\n        let k = c\n"
        "        total = total + await k.bump(1) % 7\n        i = i + 1\n    }\n    return total\n}\n"
        "#main\nasync fun main() {\n    print(await churn(200000))\n}\n"),
    "actor_reentrancy_one_task": (
        "actor A {\n    n: int\n}\nactor B {\n    m: int\n}\n"
        "impl A {\n    async fun ping(self, b: B) -> int {\n        return await b.pong(self)\n    }\n"
        "    fun val(self) -> int {\n        return self.n\n    }\n}\n"
        "impl B {\n    async fun pong(self, a: A) -> int {\n        return await a.val() + self.m\n    }\n}\n"
        "#main\nasync fun main() {\n    let a = A { n: 1 }\n    let b = B { m: 2 }\n"
        "    print(await a.ping(b))\n    print(await a.ping(b) + await b.pong(a))\n}\n"),
    "recursive_actors": (
        "actor Node {\n    val: int,\n    next: Option<Node>,\n}\n"
        "impl Node {\n    async fun sum(self) -> int {\n        return match self.next {\n"
        "            Some(n) => self.val + await n.sum(),\n            None => self.val,\n        }\n    }\n"
        "    fun link(var self, n: Node) {\n        self.next = Some(n)\n    }\n}\n"
        "#main\nasync fun main() {\n    var head = Node { val: 0, next: None }\n    var i = 1\n"
        "    while i <= 20 {\n        let n = Node { val: i, next: Some(head) }\n        head = n\n        i = i + 1\n    }\n"
        "    print(await head.sum())\n    let tail = Node { val: 1000, next: None }\n    await tail.link(head)\n"
        "    print(await tail.sum())\n}\n"),
    # awaited `var self` methods on list elements and on a field's element
    # (MYLA-142): the element's index computed once, the method's final
    # `self` written back there; a copy of the list keeps its own (MYLA-143)
    "var_self_on_elements": 'struct Counter {\n    n: int,\n    log: [str],\n}\n\nimpl Counter {\n    async fun bump(var self, by: int) -> int {\n        self.n = self.n + by\n        push(self.log, f"+{by}")\n        return self.n\n    }\n}\n\nstruct Board {\n    rows: [Counter],\n}\n\n\nfun pick(i: int) -> int {\n    print(f"pick {i}")\n    return i\n}\n\n#main\nasync fun main() {\n    var cs = [Counter { n: 0, log: [] }, Counter { n: 10, log: [] }]\n    let a = await cs[1].bump(5)\n    let b = await cs[pick(0)].bump(2)\n    var i = 0\n    while i < 3 {\n        let c = await cs[i % 2].bump(1)\n        i = i + 1\n    }\n    var board = Board { rows: [Counter { n: 100, log: [] }] }\n    let d = await board.rows[0].bump(7)\n    let copy = cs\n    let e = await cs[0].bump(1000)\n    print(f"{a} {b} {d} {e}")\n    print(f"{cs[0].n} {cs[1].n} {len(cs[0].log)} {len(cs[1].log)} {board.rows[0].n} {copy[0].n}")\n}\n',
    # every kind of value crossing into children and actors and back (D92):
    # copied deeply where it crosses (lists, maps, strings, builders, a
    # boxed and a list-recursive enum, tuples, closures with captures), an
    # actor handle shared; what the children and the actor change never shows
    # in the parent
    "values_cross_deeply": 'import std.task as task\n\nenum Tree {\n    Leaf(str),\n    Node([Tree]),\n}\n\nenum Ex {\n    Num(int),\n    Neg(Ex),\n    Add(Ex, Ex),\n}\n\nfun eval(e: Ex) -> int {\n    return match e {\n        Ex.Num(n) => n,\n        Ex.Neg(x) => 0 - eval(x),\n        Ex.Add(a, b) => eval(a) + eval(b),\n    }\n}\n\nstruct Rec {\n    ex: Ex,\n    sb: StringBuilder,\n    name: str,\n    tags: [str],\n    scores: [str: int],\n    tree: Tree,\n    pair: (str, [int]),\n}\n\nactor Store {\n    items: [Rec],\n    names: [str: int],\n}\n\nimpl Store {\n    fun put(var self, r: Rec, extra: [str]) -> int {\n        push(self.items, r)\n        for e in extra {\n            self.names[e] = len(self.items)\n        }\n        return len(r.tags) + len(extra)\n    }\n    fun find(self, name: str) -> Rec {\n        var i = len(self.items) - 1\n        while i >= 0 {\n            if self.items[i].name == name {\n                return self.items[i]\n            }\n            i = i - 1\n        }\n        return self.items[0]\n    }\n    async fun summary(self, prefix: str) -> [str] {\n        var out: [str] = []\n        for r in self.items {\n            push(out, prefix + r.name)\n        }\n        return out\n    }\n    fun clear(var self) {\n        self.items = []\n    }\n}\n\nfun count(t: Tree) -> int {\n    return match t {\n        Tree.Leaf(s) => len(s),\n        Tree.Node(ts) => {\n            var n = 0\n            for c in ts {\n                n = n + count(c)\n            }\n            n\n        },\n    }\n}\n\nfun make(i: int) -> Rec {\n    var scores: [str: int] = [:]\n    scores[f"s{i}"] = i\n    let tree = Tree.Node([Tree.Leaf(f"leaf{i}"), Tree.Node([Tree.Leaf("x"), Tree.Leaf(f"{i}")])])\n    var sb = StringBuilder()\n    append(sb, f"sb{i}")\n    return Rec { ex: Ex.Add(Ex.Num(i), Ex.Neg(Ex.Num(2))), sb: sb, name: f"rec{i}", tags: [f"t{i}", "u"], scores: scores, tree: tree, pair: (f"p{i}", [i, i + 1]) }\n}\n\nasync fun work(r: Rec, s: Store, f: (int) -> int) -> int {\n    let k = await s.put(r, r.tags)\n    let back = await s.find(r.name)\n    var sb = StringBuilder()\n    append(sb, back.name)\n    var bsb = back.sb\n    append(bsb, "!")\n    let text = build(sb) + build(bsb)\n    return k + eval(back.ex) + count(back.tree) + len(text) + f(len(back.pair.1))\n}\n\n#main\nasync fun main() {\n    let s = Store { items: [], names: [:] }\n    var total = 0\n    var round = 0\n    while round < 300 {\n        let base = round * 3\n        let add = (x: int) => x + base\n        var r = make(round)\n        async let a = work(r, s, add)\n        r.name = "changed"\n        push(r.tags, "parent")\n        async let b = work(make(round + 1), s, add)\n        var fs: [async () -> int] = []\n        for j in 0..3 {\n            let rj = make(j)\n            push(fs, async () => count(rj.tree) + len(rj.name))\n        }\n        let rs = await task.all(fs)\n        for x in rs {\n            total = total + x\n        }\n        total = total + await a + await b + len(r.tags)\n        let sm = await s.summary("> ")\n        var chars = 0\n        for line in sm {\n            chars = chars + len(line)\n        }\n        total = total + len(sm) * 1000 + chars\n        if round % 50 == 49 {\n            await s.clear()\n        }\n        round = round + 1\n    }\n    print(total)\n}\n',
    # an awaited `var self` method of a struct on a frame: its final `self`
    # goes back to the receiver, a variable or a field of one, releasing the
    # old value
    "var_self_write_back": (
        "struct Log { lines: [str], name: str }\n"
        "impl Log {\n    async fun add(var self, s: str) -> int {\n        push(self.lines, s)\n"
        "        self.name = self.name + \".\"\n        return len(self.lines)\n    }\n"
        "    async fun reset(var self) {\n        self.lines = []\n    }\n}\n"
        "struct Box { log: Log, n: int }\n"
        "async fun run() -> int {\n    var b = Box { log: Log { lines: [], name: \"x\" }, n: 0 }\n"
        "    var total = 0\n    var i = 0\n    while i < 20000 {\n"
        "        let k = await b.log.add(f\"line {i}\")\n        total = total + k\n"
        "        if k == 50 { await b.log.reset() }\n        i = i + 1\n    }\n"
        "    var l = Log { lines: [\"a\"], name: \"y\" }\n    let m = await l.add(\"b\")\n"
        "    print(f\"{m} {len(l.lines)} {len(l.name)} {len(b.log.lines)} {len(b.log.name)}\")\n"
        "    return total\n}\n"
        "#main\nasync fun main() {\n    print(await run())\n}\n"),
}


_HELD_COUNTER = ("actor C { n: int }\nimpl C {\n    fun bump(var self) -> int {\n"
                 "        self.n = self.n + 1\n        return self.n\n    }\n}\n")
# (program, stdout, exit code, the start of stderr)
CHILD_FAILURES = {
    # main stops at its next call of the actor, before `await b` (D97)
    "held_panic": (_HELD_COUNTER + (
        "async fun boom(c: C) -> int {\n    let x = await c.bump()\n    panic(\"boom\")\n    return 0\n}\n"
        "async fun fine(c: C) -> int {\n    return await c.bump() * 10\n}\n"
        "#main\nasync fun main() {\n    let c = C { n: 0 }\n    async let a = boom(c)\n    async let b = fine(c)\n"
        "    var i = 0\n    while i < 5 {\n        print(await c.bump())\n        i = i + 1\n    }\n"
        "    print(await b)\n    print(\"before a\")\n    print(await a)\n    print(\"never\")\n}\n"),
        "1\n", 1, "runtime error: boom\n"),
    # a grandchild's `exit` ends the program before main is done counting
    "held_exit": ("from std.process import exit\n" + _HELD_COUNTER + (
        "async fun leave(c: C) {\n    let x = await c.bump()\n    exit(4)\n}\n"
        "async fun inner(c: C) -> int {\n    async let l = leave(c)\n    let y = await c.bump()\n"
        "    print(\"inner goes on\")\n    return y\n}\n"
        "#main\nasync fun main() {\n    let c = C { n: 0 }\n    async let a = inner(c)\n"
        "    for i in 0..4 {\n        print(await c.bump())\n    }\n    print(\"waiting\")\n"
        "    print(await a)\n    print(\"never\")\n}\n"),
        "1\ninner goes on\n3\n", 4, ""),
    # children of synchronous calls are tasks too: they run when the parent
    # waits, here at its `await`, which their failure stops
    "held_sync_child": (
        "fun noisy(i: int) -> int {\n    print(f\"noisy {i}\")\n    return i * 2\n}\n"
        "fun pick(xs: [int], i: int) -> int {\n    return xs[i]\n}\n"
        "#main\nasync fun main() {\n    async let a = noisy(1)\n    print(\"parent\")\n    print(await a)\n"
        "    async let b = pick([1, 2], 5)\n    print(\"between\")\n    print(await b)\n}\n",
        "parent\nnoisy 1\n2\nbetween\n", 1, "runtime error: index out of bounds\n"),
    # an out-of-bounds index in a child that is never awaited: its scope's end
    "held_trap": (
        "async fun pick(xs: [int], i: int) -> int {\n    return xs[i]\n}\n"
        "#main\nasync fun main() {\n    if true {\n        async let a = pick([1, 2], 5)\n"
        "        print(\"in scope\")\n    }\n    print(\"never\")\n}\n",
        "in scope\n", 1, "runtime error: index out of bounds\n"),
}


# A binary tree of 4,096 small child tasks: workers steal the oldest frames,
# the biggest pieces of the tree (MYLA-140).
TASK_TREE = """\
fun work(n: int) -> int {
    var x = n
    var i = 0
    while i < 200 {
        x = (x * 17 + 5) % 1009
        i = i + 1
    }
    return x
}

async fun tree(depth: int, n: int) -> int {
    if depth == 0 {
        return work(n)
    }
    async let a = tree(depth - 1, n * 2)
    async let b = tree(depth - 1, n * 2 + 1)
    return (await a + await b) % 1000003
}

#main
async fun main() {
    print(await tree(12, 1))
}
"""

# Eight children each crunching numbers for a while; prints 1 when the results
# agree with one another.
PARALLEL_WORK = """\
import std.task as task

fun crunch(seed: int64) -> int64 {
    var x: int64 = seed
    var acc: int64 = 0
    var i = 0
    while i < 15000000 {
        x = (x * 48271) % 2147483647
        acc = (acc + x % 7) % 1000000007
        i = i + 1
    }
    return acc - acc + 1
}

#main
async fun main() {
    var fs: [async () -> int64] = []
    for k in 0..8 {
        let seed: int64 = (k + 1) as int64
        push(fs, async () => crunch(seed))
    }
    var ones: int64 = 0
    for r in await task.all(fs) {
        ones = ones + r
    }
    print(ones / 8)
}
"""

# The program's CPU time (user and system) and wall time, on stderr.
_CPU_AND_WALL = (
    "import resource, subprocess, sys, time\n"
    "t = time.time()\n"
    "p = subprocess.run(sys.argv[1:], capture_output=True, text=True)\n"
    "wall = time.time() - t\n"
    "u = resource.getrusage(resource.RUSAGE_CHILDREN)\n"
    "sys.stdout.write(p.stdout)\n"
    "sys.stderr.write(f'{u.ru_utime + u.ru_stime} {wall}')\n"
)


DEEP_TASKS = """\
import std.task as task

actor Counter {
    count: int
}

impl Counter {
    fun add(var self, n: int) -> int {
        self.count = self.count + 1
        return self.count
    }
    fun get(self) -> int {
        return self.count
    }
}

async fun work(c: Counter, i: int) -> int {
    let x = await c.add(i)
    return i * 2
}

async fun down(n: int) -> int {
    if n == 0 {
        return 0
    }
    return 1 + await down(n - 1)
}

#main
async fun main() {
    let c = Counter { count: 0 }
    var fs: [async () -> int] = []
    for i in 0..3000 {
        push(fs, async () => await work(c, i))
    }
    let rs = await task.all(fs)
    var sum = 0
    for r in rs {
        sum = sum + r
    }
    print(sum)
    print(await c.get())
    print(await down(100000))
}
"""


IR_SAMPLE = """\
fun scale(x: int32, by: int32) -> int32 {
    if x > 100 {
        return x
    }
    return x * by
}

fun main() {
    print(scale(7, 6))
}
"""

IR_SAMPLE_TEXT = """\
fun myla_scale -> int32 {
  $0 x: int32 (argument 0)
  $1 by: int32 (argument 1)
L0:
  bind x $0
  bind by $1
  scope open
  loc 2 5
  %t0 = load $0
  %t1 = const int32 100
  %t2 = cmp > int32 %t0, %t1
  br %t2, L1, L2
L1:
  scope open
  loc 3 9
  %t3 = load $0
  ret %t3
L3:
  scope close
  jmp L2
L2:
  loc 5 5
  %t4 = load $0
  %t5 = load $1
  %t6 = * int32 %t4, %t5 @5:14
  ret %t6
L4:
  scope close
  ret
}
"""


if __name__ == "__main__":
    unittest.main()
