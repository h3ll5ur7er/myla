"""Differential burn test for the self-hosted interpreter (self-hosting v0.8).

`selfhost/interp.my` is the Myla-written tree-walking interpreter;
`selfhost/interp_main.my` loads a program, type-checks it (with the same
`Option`/`Result` prelude the Python `run` injects), then interprets it — producing the same stdout and exit status
as `myla run` (the Python interpreter). This test asserts that, for every
runnable example in the corpus, the self-hosted interpreter's (stdout, exit
code) is identical to the Python oracle's. That is the v0.8 interpreter-parity
gate from docs/Development/Testing.md (the Myla-built binary had to produce
the same stdout/exit code as the Python-built one and the interpreter, for
every example).

As with the lexer/parser/checker gates, the Myla interpreter runs as a *native
binary*, built by the self-hosted compiler (which also exercises codegen parity
of the toolchain); a host that can't build one skips the gate. (It used to fall
back to running the interpreter source through the Python interpreter; the
self-hosted interpreter can't stand in, as it needs a native build too.)

The Python oracle's answers are recorded (`tests/burn/_golden.py`, MYLA-219):
the oracle functions below run the retired Python toolchain only when
recording.

Scope. The corpus gate covers the single-file top-level examples (`floats.my`
included since MYLA-29). `interp_main` links its input with the self-hosted
module loader (MYLA-30), so the multi-module programs of the codegen gate
(`examples/modules` and its MODULE_PROJECTS) run here too, against the Python
`link` + interpreter.
"""
from __future__ import annotations

import glob
import io
import os
import subprocess
import tempfile
import time
import unittest

from ._golden import NoGolden, answered_or_recorded, golden, recorded_examples
from ._native import CAN_BUILD_NATIVE
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)

# Examples outside the v0.8 interpreter gate's scope (see module docstring).
EXCLUDED: set[str] = set()


def _corpus() -> list[str]:
    """Every single-file top-level example the recordings cover (an example
    added since is held to test_examples_run's expectation, MYLA-288). The
    import-driven multi-file packages live in subdirectories."""
    return [f for f in recorded_examples() if os.path.basename(f) not in EXCLUDED]


@golden("selfhost_interp.run")
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


def _modules(entry: str) -> list[str]:
    """The files of the project whose entry is `entry` besides the entry, so
    that a recorded answer is keyed by every module of the program."""
    root = os.path.dirname(entry)
    files = glob.glob(os.path.join(root, "**", "*.my"), recursive=True)
    return sorted(f for f in files if f != entry)


@golden("selfhost_interp.cli_run")
def _cli_oracle(entry: str, modules: list[str]) -> tuple[str, str, int]:
    """(stdout, stderr, exit code) of the Python `myla run` for `entry`: its
    output, then a runtime error rendered as the CLI prints it. `modules`
    (the program's other files) only key the recorded answer."""
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


def _main(*lines: str, before: str = "") -> str:
    body = "".join(f"    {line}\n" for line in lines)
    return f"{before}fun main() {{\n{body}}}\n"


_TRACE = ("fun at(tag: str, i: int) -> int {\n    print(tag)\n    return i\n}\n"
          "struct C { n: int }\nimpl C {\n    fun bump(var self, d: int) -> int {\n"
          "        self.n = self.n + d\n        return self.n\n    }\n}\n")

# The Python interpreter's behaviour the self-hosted one diverged from
# (MYLA-32): runtime errors with their message and position, the order and
# count of evaluations, unsigned shifts, ranges beyond int32.
INTERP_PROGRAMS = {
    "panic_message": _main("print(1)", "panic(\"boom\")", "print(2)"),
    "assert_message": _main("assert(1 < 2, \"fine\")", "assert(1 > 2, \"math\")"),
    "assert_default_message": _main("assert(false)"),
    "unreachable": _main("unreachable()"),
    "division_by_zero": _main("let z = 0", "print(10 / z)"),
    "modulo_by_zero": _main("let z = 0", "print(10 % z)"),
    "missing_str_key": _main("let m = [\"a\": 1]", "print(m[\"it's\"])"),
    "missing_bool_key": _main("let m = [true: 1]", "print(m[false])"),
    "list_store_out_of_bounds": _main("var xs = [1, 2]", "xs[2] = 3"),
    "nested_store_out_of_bounds": _main("var xs = [[1], [2]]", "xs[3][0] = 3"),
    "pop_empty": _main("var xs: [int] = []", "let x = xs.pop()"),
    "no_entry_point": "fun helper() -> int {\n    return 1\n}\n",
    "error_inside_print_stops_it": _main("let xs = [1]", "print(xs[1] + 1)", "print(9)"),
    "unsigned_shift": _main("let x: uint64 = 18446744073709551615", "print(x >> 60)", "let y: int64 = -16", "print(y >> 2)"),
    "range_beyond_int32": _main("for i in 3000000000..3000000002 {", "    print(i)", "}"),
    "receiver_before_arguments": _main("var cs = [C { n: 0 }]", "print(cs[at(\"recv\", 0)].bump(at(\"arg\", 5)))",
                                       "print(cs[0].n)", before=_TRACE),
    "store_target_evaluated_once": _main("var xs = [[0, 0], [0, 0]]", "xs[at(\"a\", 1)][at(\"b\", 0)] = at(\"v\", 7)",
                                         "print(xs[1][0])", before=_TRACE),
    "push_target_evaluated_once": _main("var xs = [[0], [0]]", "xs[at(\"a\", 1)].push(at(\"v\", 7))",
                                        "print(xs[1].len())", before=_TRACE),
    "string_comparison": _main("let s = \"\"", "print(s == \"\")", "print(\"ab\" != \"ab\")", "print(\"a\" + \"b\" == \"ab\")"),
    "map_store_inserts": _main("var m = [\"a\": [1]]", "m[\"b\"] = [2, 3]", "print(m[\"b\"].len())"),
    # the int64 minimum divided by anything but -1 (found by std.toml, MYLA-89)
    "int64_min_divided": _main("let a: int64 = -9223372036854775807 - 1", "print(a / 10)", "print(a % 10)",
                               "print(a / -10)", "print(a % -7)", "print(a / 3)", "print(a / -1)"),
    # `?` returning early out of a destructuring `let` (found by std.toml, MYLA-89)
    "try_in_destructuring_let": _main("match first(true) { Ok(n) => print(n), Err(e) => print(e) }",
                                      "match first(false) { Ok(n) => print(n), Err(e) => print(e) }", before=(
        "fun pair(ok: bool) -> Result<(int, str), str> {\n"
        "    if ok { return Ok((1, \"one\")) }\n"
        "    return Err(\"no pair\")\n"
        "}\n"
        "fun first(ok: bool) -> Result<int, str> {\n"
        "    let (n, s) = pair(ok)?\n"
        "    return Ok(n)\n"
        "}\n")),
}

# The programs above whose meaning D175 changed: the minimum divided by -1
# wraps no more where overflow is checked; what they print before it.
OVERFLOWS = {
    "int64_min_divided": "-922337203685477580\n-8\n922337203685477580\n-1\n-3074457345618258602\n",
}



_FETCH = "async fun fetch(n: int) -> int {\n    return n * 10\n}\n"
_COUNTER = ("actor Counter {\n    count: int\n}\n"
            "impl Counter {\n"
            "    fun increment(var self) -> int {\n        self.count = self.count + 1\n        return self.count\n    }\n"
            "    fun get(self) -> int {\n        return self.count\n    }\n}\n")


def _amain(*lines: str, before: str = "") -> str:
    body = "".join(f"    {line}\n" for line in lines)
    return f"{before}#main\nasync fun main() {{\n{body}}}\n"


# Concurrency (D89, MYLA-139): what each prints doesn't depend on the order of
# the tasks running at once, so the self-hosted interpreter, which runs a
# child to its end when it starts, must print what the Python one does.
CONCURRENCY_PROGRAMS = {
    "await_calls": _amain("print(await fetch(4))", "print(await fetch(1) + await fetch(2))", before=_FETCH),
    "async_values": _amain("let f = async (n: int) => await fetch(n) + 1", "print(await apply(f, 2))",
                           "print(await apply(fetch, 3))", before=_FETCH + (
        "async fun apply(f: async (int) -> int, x: int) -> int {\n    return await f(x)\n}\n")),
    "async_method": _amain("let p = P { x: 21 }", "print(await p.twice())", before=(
        "struct P { x: int }\nimpl P {\n    async fun twice(self) -> int {\n        return self.x * 2\n    }\n}\n")),
    "async_let_results": _amain("async let a = fetch(1)", "async let b: int = fetch(2)", "print(await a + await b)",
                                "print(await a)", before=_FETCH),
    "scopes_wait_for_children": _amain("if true {", "    async let a = noisy(0)", "}", "for i in 1..3 {",
                                       "    async let b = noisy(i)", "}", "print(\"after\")",
                                       before="async fun noisy(i: int) {\n    print(i)\n}\n"),
    "children_work_on_copies": _amain("var xs = [1, 2, 3]", "async let t = total(xs)", "xs[0] = 100",
                                      "print(await t)", "print(xs[0])", "var p = P { x: 1 }",
                                      "async let r = p.bump()", "print(p.x)", "print(await r)", before=(
        "async fun total(xs: [int]) -> int {\n    var t = 0\n    for x in xs {\n        t = t + x\n    }\n    return t\n}\n"
        "struct P { x: int }\nimpl P {\n    fun bump(var self) -> int {\n        self.x = self.x + 1\n        return self.x\n    }\n}\n")),
    "awaited_child_fails": _amain("async let a = boom()", "print(\"between\")", "print(await a)", "print(\"never\")",
                                  before="async fun boom() -> int {\n    panic(\"boom\")\n    return 0\n}\n"),
    "unawaited_child_fails_its_scope": _amain("if true {", "    async let a = boom()", "    print(\"in scope\")", "}",
                                              "print(\"never\")", before="async fun boom() {\n    panic(\"boom\")\n}\n"),
    "child_exits": _amain("async let a = leave()", "print(\"between\")", "print(await a)", before=(
        "from std.process import exit\nasync fun leave() -> int {\n    exit(3)\n    return 0\n}\n")),
    "actor_counter": _amain("let c = Counter { count: 0 }", "async let a = count_up(c, 50)", "async let b = count_up(c, 50)",
                            "await a", "await b", "let d = c", "let x = await d.increment()", "print(await c.get())",
                            before=_COUNTER + (
        "async fun count_up(c: Counter, n: int) {\n    for i in 0..n {\n        let x = await c.increment()\n    }\n}\n")),
    "actor_copies_in_and_out": _amain("let b = Box { items: [] }", "var xs = [1, 2]", "await b.put(xs)", "xs[0] = 9",
                                      "var ys = await b.all()", "ys[1] = 7", "print(await b.first())",
                                      "print((await b.all()).len())", before=(
        "actor Box {\n    items: [int]\n}\n"
        "impl Box {\n    fun put(var self, xs: [int]) {\n        self.items = xs\n    }\n"
        "    fun all(self) -> [int] {\n        return self.items\n    }\n"
        "    fun first(self) -> int {\n        return self.items[0]\n    }\n}\n")),
    "actor_reentrancy": _amain("let a = A { n: 1 }", "let b = B { m: 2 }", "async let x = a.ping(b)",
                               "async let y = a.ping(b)", "print(await x + await y)", "let p = P { n: 1 }",
                               "let q = P { n: 10 }", "print(await p.poke(q, 10))", "print(await a.peek())", before=(
        "actor A {\n    n: int\n}\nactor B {\n    m: int\n}\n"
        "impl A {\n    async fun ping(self, b: B) -> int {\n        return await b.pong(self)\n    }\n"
        "    fun val(self) -> int {\n        return self.n\n    }\n"
        "    async fun peek(self) -> int {\n        let n = self.n\n        async let x = n + 1\n        return await x\n    }\n}\n"
        "impl B {\n    async fun pong(self, a: A) -> int {\n        return await a.val() + self.m\n    }\n}\n"
        "actor P {\n    n: int\n}\n"
        "impl P {\n    async fun poke(self, other: P, depth: int) -> int {\n"
        "        if depth == 0 {\n            return self.n\n        }\n"
        "        return await other.poke(self, depth - 1) + self.n\n    }\n}\n")),
    # needs the tasks to take turns: the child waits until its parent sets the flag
    "child_waits_for_its_parent": _amain("let f = Flag { up: false }", "async let w = wait_up(f)", "await f.raise()",
                                         "print(await w)", before=(
        "actor Flag {\n    up: bool\n}\n"
        "impl Flag {\n    fun raise(var self) {\n        self.up = true\n    }\n"
        "    fun get(self) -> bool {\n        return self.up\n    }\n}\n"
        "async fun wait_up(f: Flag) -> int {\n    var polls = 0\n"
        "    while await f.get() == false {\n        polls = polls + 1\n    }\n    return 1\n}\n")),
    "normalized_expressions": _amain(
        "var xs = [await fetch(1), 2, await fetch(3)]", "print(xs[0] + xs[2])",
        "let ok = await fetch(0) == 0 && await fetch(1) == 10", "print(ok)",
        "let no = false && await fetch(1) == 10", "print(no)",
        "let yes = true || await fetch(1) == 99", "print(yes)",
        "let s = match await fetch(2) {", "    20 => await fetch(5) + 1,", "    _ => 0,", "}", "print(s)",
        "var n = 0", "while await fetch(n) < 30 {", "    n = n + 1", "}", "print(n)",
        "for i in 0..await fetch(1) {", "    if i == 3 {", "        break", "    }", "    print(await fetch(i))", "}",
        "let p = P { x: await fetch(4), y: \"a\" }", "print(p.x)",
        "print(f\"{await fetch(7)}!\")", "print(await twice(await fetch(1)))", "print(await opt(5))", before=_FETCH + (
        "struct P { x: int, y: str }\n"
        "async fun twice(n: int) -> int {\n    async let a = fetch(n)\n    return await a / 5\n}\n"
        "async fun opt(n: int) -> int {\n    let r = await maybe(n)\n    return match r {\n"
        "        Some(v) => v,\n        None => -1,\n    }\n}\n"
        "async fun maybe(n: int) -> Option<int> {\n    let v = (await half(n))?\n    return Some(v + 100)\n}\n"
        "async fun half(n: int) -> Option<int> {\n    if n % 2 == 0 {\n        return Some(n / 2)\n    }\n    return None\n}\n")),
    "async_var_self_method": _amain("var c = C { n: 1 }", "print(await c.bump(5))", "print(c.n)", before=(
        "struct C { n: int }\nimpl C {\n    async fun bump(var self, d: int) -> int {\n"
        "        let x = await fetch(d)\n        self.n = self.n + x\n        return self.n\n    }\n}\n" + _FETCH)),
    "task_all": _amain("var fs: [async () -> int] = []", "for i in 0..9 {", "    fs.push(async () => await fetch(i))", "}",
                       "let rs = await task.all(fs)", "print(rs.len())", "print(rs[8])",
                       "let none: [async () -> str] = []", "print((await task.all(none)).len())",
                       before="import std.task as task\n" + _FETCH),
}


@golden("selfhost_interp.linked_run")
def _linked_oracle(entry: str, modules: list[str]) -> tuple[str, int]:
    """(stdout, exit code) of the Python `link` + interpreter for the program
    whose entry is `entry`; `modules` (its other files) only key the recorded
    answer."""
    from myla.interpreter import Interpreter
    from myla.loader import default_stdlib_root, link
    from myla.types import check

    out = io.StringIO()
    checker = check(link(entry, stdlib_root=default_stdlib_root()))
    code = Interpreter(checker, out, argv=[entry]).run()
    return out.getvalue(), code


class SelfHostedInterpParity(unittest.TestCase):
    _binary: str | None = None

    @classmethod
    def setUpClass(cls) -> None:
        if not CAN_BUILD_NATIVE:
            return
        # The Myla interpreter, built natively by the self-hosted compiler
        # (cached), so the gate also exercises the codegen parity of the
        # toolchain.
        cls._binary = selfhost_tool("interp_main")

    def _myla_run_full(self, path: str) -> tuple[str, str, int]:
        proc = subprocess.run(
            [self._binary, path, STDLIB_ROOT], capture_output=True, text=True
        )
        return proc.stdout, proc.stderr, proc.returncode

    def test_runtime_behaviour_matches_the_python_cli(self) -> None:
        if self._binary is None:
            self.skipTest("the self-hosted interpreter could not be built natively")
        cases = {os.path.basename(p): p for p in glob.glob(os.path.join(_REPO, "examples", "errors", "runtime_*.my"))}
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in INTERP_PROGRAMS.items():
                cases[name] = os.path.join(tmp, name + ".my")
                with open(cases[name], "w", encoding="utf-8") as fh:
                    fh.write(source)
            # a runtime error in an imported module names that module
            lib = os.path.join(tmp, "proj", "lib.my")
            os.makedirs(os.path.dirname(lib))
            with open(lib, "w", encoding="utf-8") as fh:
                fh.write("pub fun third(xs: [int]) -> int {\n    return xs[2]\n}\n")
            cases["error_in_module"] = os.path.join(tmp, "proj", "main.my")
            with open(cases["error_in_module"], "w", encoding="utf-8") as fh:
                fh.write("from .lib import third\nfun main() {\n    print(third([1, 2]))\n}\n")
            for name, path in sorted(cases.items()):
                with self.subTest(case=name):
                    modules = _modules(path) if name == "error_in_module" else []
                    if name in OVERFLOWS:
                        # D175: what the Python CLI printed before the
                        # overflow, then the overflow at its operator
                        out, err, code = self._myla_run_full(path)
                        self.assertEqual((out, code), (OVERFLOWS[name], 1))
                        self.assertTrue(err.startswith(f"runtime error: integer overflow\n  --> {path}:"), err)
                        continue
                    try:
                        want = _cli_oracle(path, modules)
                    except NoGolden:
                        if name.startswith("runtime_"):
                            continue    # added since (D175): test_error_corpus holds it
                        raise
                    self.assertEqual(self._myla_run_full(path), want)

    def test_concurrency_matches_the_python_cli(self) -> None:
        if self._binary is None:
            self.skipTest("the self-hosted interpreter could not be built natively")
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in CONCURRENCY_PROGRAMS.items():
                path = os.path.join(tmp, name + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(source)
                with self.subTest(program=name):
                    self.assertEqual(self._myla_run_full(path), _cli_oracle(path, []))

    def _myla_run(self, path: str) -> tuple[str, int]:
        if self._binary is None:
            # the fallback through the Python interpreter is retired (MYLA-219)
            self.skipTest("the self-hosted interpreter could not be built natively")
        proc = subprocess.run(
            [self._binary, path, STDLIB_ROOT], capture_output=True, text=True
        )
        return proc.stdout, proc.returncode

    def test_corpus_run_parity(self) -> None:
        checked = 0
        for path in _corpus():
            rel = os.path.relpath(path, _REPO)
            with self.subTest(file=rel):
                self.assertEqual(self._myla_run(path), answered_or_recorded(path, _oracle)[0])
                checked += 1
        # Guard against the corpus silently going empty.
        self.assertGreater(checked, 20)

    def test_parity_programs_match_the_oracle(self) -> None:
        from .test_compiler_parity import PINNED, PROGRAMS
        from .test_selfhost_codegen import PARITY_PROGRAMS

        with tempfile.TemporaryDirectory() as tmp:
            for name in PARITY_PROGRAMS:
                with self.subTest(program=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(PROGRAMS[name])
                    self.assertEqual(self._myla_run(path), (PINNED[name], 0) if name in PINNED else _oracle(path))

    def test_module_programs_match_the_oracle(self) -> None:
        from .test_selfhost_codegen import MODULE_OUTPUTS_SINCE, MODULE_PROJECTS, _write_project

        entries = {"examples/modules": os.path.join(_REPO, "examples", "modules", "main.my")}
        with tempfile.TemporaryDirectory() as tmp:
            for name, files in MODULE_PROJECTS.items():
                entries[name] = _write_project(os.path.join(tmp, name), files)
            for name, entry in entries.items():
                with self.subTest(program=name):
                    if name in MODULE_OUTPUTS_SINCE:
                        expected = (MODULE_OUTPUTS_SINCE[name], 0)
                    else:
                        expected = _linked_oracle(entry, _modules(entry))
                    self.assertEqual(self._myla_run(entry), expected)

    def test_updates_are_amortised_constant(self) -> None:
        """`push`, element assignment, a `push` inside a `var self` method and
        one into a nested list update the container in place (MYLA-74): four
        times the iterations take about four times as long, not sixteen."""
        if self._binary is None:
            self.skipTest("timing needs the natively built interpreter")
        with tempfile.TemporaryDirectory() as tmp:
            times = {}
            for n in (UPDATE_N, 4 * UPDATE_N):
                path = os.path.join(tmp, f"updates_{n}.my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(UPDATES.replace("N_ITER", str(n)))
                start = time.perf_counter()
                proc = subprocess.run([self._binary, path, STDLIB_ROOT],
                                      capture_output=True, text=True, timeout=120)
                times[n] = time.perf_counter() - start
                self.assertEqual((proc.stdout, proc.stderr, proc.returncode),
                                 (f"{4 * n}\n{n * (n + 1) // 2}\n", "", 0))
            small, large = times[UPDATE_N], times[4 * UPDATE_N]
            self.assertLess(large, 8 * small + 0.5, f"{UPDATE_N}: {small:.2f} s, {4 * UPDATE_N}: {large:.2f} s")

    def test_byte_streams_hold_no_value_per_byte(self) -> None:
        """`io.copy` of 32 MB from a file to a file, in chunks of `[uint8]`,
        costs about what reading the file in one primitive does: the bytes
        stay a host string (MYLA-414, the 2026-11-10 review's S2: 2,096 ms,
        a value per byte, against 27 ms before D177)."""
        if self._binary is None:
            self.skipTest("timing needs the natively built interpreter")
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = os.path.join(tmp, "src.bin"), os.path.join(tmp, "dst.bin")
            with open(src, "wb") as fh:
                fh.write(os.urandom(1 << 20) * 32)
            path = os.path.join(tmp, "copy.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(BYTE_COPY)
            proc = subprocess.run([selfhost_tool("main"), "run", "--stdlib", STDLIB_ROOT, path, src, dst],
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual((proc.stderr, proc.returncode), ("", 0))
            read_ms, copy_ms = (int(x) for x in proc.stdout.split())
            with open(src, "rb") as a, open(dst, "rb") as b:
                self.assertTrue(a.read() == b.read())
            self.assertLess(copy_ms, 10 * read_ms + 500, f"read {read_ms} ms, copy {copy_ms} ms")

    def test_generic_recursion_binds_its_types_in_constant_memory(self) -> None:
        """A generic function recursing through two call sites takes the
        memory the same function on `int` takes: its type parameters' binding
        is one environment, not one per call path (MYLA-414, the 2026-11-12
        review's C3: `fib(27)` 163 MB against 13 MB)."""
        if self._binary is None:
            self.skipTest("measuring needs the natively built interpreter")
        peaks = {}
        with tempfile.TemporaryDirectory() as tmp:
            for name, sig in (("int", "fib(n: int, one: int, two: int) -> int"),
                              ("generic", "fib<T: Add + Sub + Ord>(n: T, one: T, two: T) -> T")):
                path = os.path.join(tmp, name + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(GENERIC_FIB.replace("SIGNATURE", sig))
                out, peaks[name] = _peak_mb([selfhost_tool("main"), "run", "--stdlib", STDLIB_ROOT, path])
                self.assertEqual(out, "75025\n")
        self.assertLess(peaks["generic"], peaks["int"] + 8, peaks)

    def test_a_builder_takes_its_size(self) -> None:
        """A `StringBuilder` holds its bytes packed, as natively: building a
        string of 20 MB takes about 20 MB for the string and at most twice
        that for the builder (MYLA-600: a word a byte, 280 MB against
        55 MB natively)."""
        if self._binary is None:
            self.skipTest("measuring needs the natively built interpreter")
        with tempfile.TemporaryDirectory() as tmp:
            peaks = {}
            for name, program in (("empty", "fun main() {\n    print(20480000)\n}\n"), ("build", BUILD_20MB)):
                path = os.path.join(tmp, name + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(program)
                out, peaks[name] = _peak_mb([selfhost_tool("main"), "run", "--stdlib", STDLIB_ROOT, path])
                self.assertEqual(out, "20480000\n")
        self.assertLess(peaks["build"], peaks["empty"] + 60, peaks)


    def test_lines_and_extended_bytes_take_no_step_a_byte(self) -> None:
        """`read_line` and `extend` of `[uint8]` cost what the lines or the
        reads do, not their bytes: 6,000 lines of 500 bytes take about what
        6,000 lines of 5 do (MYLA-546: 3 MB in 60,000 lines were slow, the
        interpreter scanning for each line's end a byte at a time and
        `extend` pushing each byte)."""
        if self._binary is None:
            self.skipTest("timing needs the natively built interpreter")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bytes.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(LINES_AND_EXTENDS)
            for mode in ("lines", "extend"):
                times = {}
                for width in (5, 500):
                    data = os.path.join(tmp, f"{width}.txt")
                    with open(data, "wb") as fh:
                        fh.write((b"x" * width + b"\n") * 6000)
                    with open(data, "rb") as stdin:
                        start = time.perf_counter()
                        proc = subprocess.run([selfhost_tool("main"), "run", "--stdlib", STDLIB_ROOT, path, mode, str(width + 1)],
                                              stdin=stdin, capture_output=True, text=True, timeout=120)
                        times[width] = time.perf_counter() - start
                    self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (f"6000 {6000 * (width + 1)}\n", "", 0))
                with self.subTest(mode=mode):
                    self.assertLess(times[500], 3 * times[5] + 0.5, f"{mode}: 5 bytes {times[5]:.2f} s, 500 bytes {times[500]:.2f} s")

    @unittest.skipIf(not os.path.isdir("/proc/self/task"), "counts the wake-ups in /proc")
    def test_an_idle_server_sleeps(self) -> None:
        """An interpreted server waiting for connections, and for requests
        on 900 kept ones, wakes a few dozen times a second and uses a few
        percent of a CPU (MYLA-546: a poll a parked socket every millisecond;
        before, 894 wake-ups a second with none, 677 and 26.5 percent with
        900; natively none)."""
        if self._binary is None:
            self.skipTest("the self-hosted interpreter could not be built natively")
        import resource
        import socket
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if hard != resource.RLIM_INFINITY and hard < 2048:
            self.skipTest(f"900 connections need 2,048 descriptors, the limit is {hard}")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "idle.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(IDLE_SERVER)
            # the server inherits the limit
            resource.setrlimit(resource.RLIMIT_NOFILE, (max(soft, 2048), hard))
            try:
                proc = subprocess.Popen([selfhost_tool("main"), "run", "--stdlib", STDLIB_ROOT, path],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            finally:
                resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
            kept = []
            try:
                port = int(proc.stdout.readline())
                for n in (0, 900):
                    while len(kept) < n:
                        kept.append(socket.create_connection(("127.0.0.1", port), timeout=10))
                    time.sleep(1.0)
                    w0, c0 = _wake_ups(proc.pid), _cpu_seconds(proc.pid)
                    time.sleep(2.0)
                    wakes, cpu = (_wake_ups(proc.pid) - w0) / 2, 100 * (_cpu_seconds(proc.pid) - c0) / 2
                    with self.subTest(connections=n):
                        self.assertLess(wakes, 250, f"{wakes:.0f} wake-ups a second")
                        self.assertLess(cpu, 12, f"{cpu:.1f} percent of a CPU")
                # a kept connection is still served
                kept[0].sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
                kept[0].settimeout(10)
                self.assertTrue(kept[0].recv(4096).startswith(b"HTTP/1.1 200 OK\r\n"))
            finally:
                for s in kept:
                    s.close()
                proc.kill()
                proc.communicate()

    def _run_waiting(self, path: str, *argv: str) -> tuple[str, str, int, float]:
        """`myla run path argv`, its standard input a pipe that stays empty
        and open: (stdout, stderr, status, seconds until it ended); killed
        after 30 s."""
        r, w = os.pipe()
        start = time.perf_counter()
        try:
            proc = subprocess.Popen([selfhost_tool("main"), "run", "--stdlib", STDLIB_ROOT, path, *argv],
                                    stdin=r, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            os.close(r)
            r = -1
            try:
                out, err = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, err = proc.communicate()
            return out, err, proc.returncode, time.perf_counter() - start
        finally:
            if r >= 0:
                os.close(r)
            os.close(w)

    def test_a_turn_costs_nothing_per_waiting_task(self) -> None:
        """While tasks are ready, the tasks waiting for input are looked at
        now and then, not at every turn: 20,000 turns take about as long
        with 400 tasks waiting for the standard input as with none
        (MYLA-604: a poll a waiting task a turn, 2,321 ms against 151 ms)."""
        if self._binary is None:
            self.skipTest("timing needs the natively built interpreter")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "waiters.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(WAITERS)
            ms = {}
            for n in (0, 400):
                out, err, code, _ = self._run_waiting(path, str(n))
                self.assertEqual((err, code), ("", 0))
                ms[n] = int(out.split()[-2])
        self.assertLess(ms[400], 2 * ms[0] + 100, ms)

    def test_exit_ends_the_tasks_that_wait(self) -> None:
        """The entry's `exit` ends the program at once while its children
        sleep or wait for input, as natively (MYLA-620: it waited for the
        sleep's time, and for input that never came)."""
        if self._binary is None:
            self.skipTest("timing needs the natively built interpreter")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "exit.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(EXIT_WHILE_WAITING)
            for mode in ("sleep", "input", "notifier"):
                with self.subTest(mode=mode):
                    out, err, code, took = self._run_waiting(path, mode)
                    self.assertEqual((out, err, code), ("exit\n", "", 3))
                    self.assertLess(took, 5.0)


def _cpu_seconds(pid: int) -> float:
    """The CPU time the process `pid` has used (Linux's /proc)."""
    with open(f"/proc/{pid}/stat") as fh:
        fields = fh.read().rsplit(")", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")


def _wake_ups(pid: int) -> int:
    """How many times the threads of the process `pid` have given up the
    CPU (their context switches, Linux's /proc)."""
    n = 0
    for t in os.listdir(f"/proc/{pid}/task"):
        with open(f"/proc/{pid}/task/{t}/status") as fh:
            for line in fh:
                if line.startswith(("voluntary_ctxt_switches", "nonvoluntary_ctxt_switches")):
                    n += int(line.split()[1])
    return n


def _peak_mb(cmd: list[str]) -> tuple[str, float]:
    """(stdout, peak resident memory in MB) of running `cmd`, which must
    succeed."""
    with tempfile.TemporaryFile() as out:
        pid = os.fork()
        if pid == 0:
            try:
                os.dup2(out.fileno(), 1)
                os.execv(cmd[0], cmd)
            finally:
                os._exit(127)
        _, status, usage = os.wait4(pid, 0)
        out.seek(0)
        assert os.waitstatus_to_exitcode(status) == 0
        return out.read().decode(), usage.ru_maxrss / 1024


# A recursion through two call sites (test_generic_recursion_binds_its_types_in_constant_memory).
GENERIC_FIB = """\
fun SIGNATURE {
    if n < two { return n }
    return fib(n - one, one, two) + fib(n - two, one, two)
}

fun main() {
    print(fib(25, 1, 2))
}
"""


# N tasks wait for input on the standard input (a pipe that stays empty);
# meanwhile one task takes 20,000 turns: how long they take
# (test_a_turn_costs_nothing_per_waiting_task).
WAITERS = """\
import std.task as task
import std.time as time
from std.io import stdin
from std.process import args, exit
from std.num import parse_int

async fun reader() -> int {
    var r = stdin()
    return match await r.read_line_async() {
        Ok(Some(l)) => l.len()
        _ => 0
    }
}

async fun spin() -> int {
    let t = time.now_ms()
    var i = 0
    while i < 20000 {
        await task.yield()
        i += 1
    }
    return (time.now_ms() - t) as int
}

#main
async fun main() {
    let n = match parse_int(args()[1]) { Some(v) => v as int, None => 0 }
    var fs: [async () -> int] = []
    for k in 0..n { fs.push(async () => await reader()) }
    async let all = task.all(fs)
    let ms = await spin()
    print(f"{n} waiting: 20,000 turns in {ms} ms")
    exit(0)
}
"""

# The entry exits while a child sleeps, waits for input or waits on a
# notifier (test_exit_ends_the_tasks_that_wait).
EXIT_WHILE_WAITING = """\
import std.task as task
from std.io import stdin
from std.process import args, exit

async fun child(mode: str, n: task.Notifier) -> int {
    if mode == "sleep" {
        await task.sleep(60000)
    } else if mode == "input" {
        var r = stdin()
        let l = await r.read_line_async()
    } else {
        let woken = await n.wait()
    }
    print("child")
    return 1
}

#main
async fun main() {
    let n = task.notifier()
    async let a = child(args()[1], n)
    await task.yield()
    print("exit")
    exit(3)
}
"""


# A string of 20 MB built by 5,000 appends (test_a_builder_takes_its_size).
BUILD_20MB = """\
fun main() {
    var block = "0000000000000000"
    while block.len() < 4096 {
        block = block + block
    }
    var sb = StringBuilder()
    for i in 0..5000 {
        sb.append(block)
    }
    let s = sb.build()
    print(s.len())
}
"""


# A loop of in-place updates (test_updates_are_amortised_constant).
UPDATE_N = 20000
UPDATES = """\
struct Bag { items: [int] }

impl Bag {
    fun add(var self, x: int) {
        self.items.push(x)
    }
}

fun main() {
    var xs: [int] = []
    var bag = Bag { items: [] }
    var grid: [[int]] = [[]]
    var i = 0
    while i < N_ITER {
        xs.push(i)
        xs[i] = xs[i] + 1
        bag.add(i)
        grid[0].push(i)
        i = i + 1
    }
    var total: int64 = 0
    for x in xs {
        total = total + (x as int64)
    }
    print(xs.len() + bag.items.len() + grid[0].len() + xs.len())
    print(total)
}
"""

# The standard input's lines read, or its bytes read `n` at a time and
# gathered with `extend` (test_lines_and_extended_bytes_take_no_step_a_byte):
# how many and their bytes (each line's "\n" counted).
LINES_AND_EXTENDS = """\
import std.io as io
from std.io import Read, stdin
from std.process import args
from std.num import parse_int

fun main() {
    let a = args()
    var count = 0
    var bytes = 0
    if a[1] == "lines" {
        var r = stdin()
        while let Ok(Some(l)) = r.read_line() {
            count += 1
            bytes += l.len() + 1
        }
    } else {
        let n = match parse_int(a[2]) { Some(v) => v as int, None => 1 }
        var f = io.fd_stream(0)
        var all: [uint8] = []
        while true {
            let chunk = match f.read(n) { Ok(b) => b, Err(e) => { panic("read") } }
            if chunk.len() == 0 { break }
            all.extend(chunk)
            count += 1
        }
        bytes = all.len()
    }
    print(f"{count} {bytes}")
}
"""

# A server that keeps 1,000 connections a minute, its port on the first line
# (test_an_idle_server_sleeps).
IDLE_SERVER = """\
import std.http as http
from std.http import Request, Response
import std.net as net
from std.io import println

async fun handle(r: Request) -> Response {
    return http.response(200, "ok")
}

#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("can't listen") }
    }
    match l.local_addr() {
        Ok(at) => println(f"{at.port}")
        Err(e) => { panic("addr") }
    }
    var o = http.server_options()
    o.max_connections = 1000
    o.idle_ms = 60000
    o.read_ms = 60000
    match await http.serve_with(l, o, handle) {
        Ok(n) => println(f"served {n}")
        Err(e) => println(f"server: {e}")
    }
}
"""

# A file read whole, then copied in chunks (test_byte_streams_hold_no_value_per_byte):
# the milliseconds each took.
BYTE_COPY = """\
import std.fs as fs
import std.io as io
import std.time as time
from std.process import args

fun main() {
    let a = args()
    var t = time.now_ms()
    let whole = match fs.read_to_string(a[1]) { Ok(s) => s, Err(e) => { panic("read") } }
    let read_ms = time.now_ms() - t
    let src = match fs.open(a[1]) { Ok(f) => f, Err(e) => { panic("open") } }
    let dst = match fs.create(a[2]) { Ok(f) => f, Err(e) => { panic("create") } }
    t = time.now_ms()
    match io.copy(src, dst) {
        Ok(d) => print(f"{read_ms} {time.now_ms() - t}")
        Err(e) => panic("copy")
    }
    if whole.len() == 0 { panic("empty") }
}
"""


if __name__ == "__main__":
    unittest.main()
