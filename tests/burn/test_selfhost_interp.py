"""Differential burn test for the self-hosted interpreter (self-hosting v0.8).

`selfhost/interp.my` is the Myla-written tree-walking interpreter;
`selfhost/interp_main.my` loads a program, type-checks it (with the same
`Option`/`Result`/`get` prelude the Python `run` injects), then interprets it — producing the same stdout and exit status
as `myla run` (the Python interpreter). This test asserts that, for every
runnable example in the corpus, the self-hosted interpreter's (stdout, exit
code) is identical to the Python oracle's. That is the v0.8 interpreter-parity
gate from docs/self-hosting.md ("the Myla-built binary must produce the same
stdout/exit code as the Python-built one and the interpreter, for every
example").

As with the lexer/parser/checker gates, the Myla interpreter runs as a *native
binary* when the host can build one (which also exercises codegen parity of the
toolchain); otherwise it falls back to running the interpreter source through
the Python interpreter.

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
import unittest

from myla.errors import MylaError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.loader import default_stdlib_root, link
from myla.parser import parse
from myla.types import check

from ._native import CAN_BUILD_NATIVE

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
INTERP_TOOL = os.path.join(_REPO, "selfhost", "interp_main.my")

# Examples outside the v0.8 interpreter gate's scope (see module docstring).
EXCLUDED: set[str] = set()


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


def _cli_oracle(entry: str) -> tuple[str, str, int]:
    """(stdout, stderr, exit code) of the Python `myla run` for `entry`: its
    output, then a runtime error rendered as the CLI prints it."""
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
    "pop_empty": _main("var xs: [int] = []", "let x = pop(xs)"),
    "no_entry_point": "fun helper() -> int {\n    return 1\n}\n",
    "error_inside_print_stops_it": _main("let xs = [1]", "print(xs[1] + 1)", "print(9)"),
    "unsigned_shift": _main("let x: uint64 = 0u64 - 1u64", "print(x >> 60)", "let y: int64 = -16", "print(y >> 2)"),
    "range_beyond_int32": _main("for i in 3000000000..3000000002 {", "    print(i)", "}"),
    "receiver_before_arguments": _main("var cs = [C { n: 0 }]", "print(cs[at(\"recv\", 0)].bump(at(\"arg\", 5)))",
                                       "print(cs[0].n)", before=_TRACE),
    "store_target_evaluated_once": _main("var xs = [[0, 0], [0, 0]]", "xs[at(\"a\", 1)][at(\"b\", 0)] = at(\"v\", 7)",
                                         "print(xs[1][0])", before=_TRACE),
    "push_target_evaluated_once": _main("var xs = [[0], [0]]", "push(xs[at(\"a\", 1)], at(\"v\", 7))",
                                        "print(len(xs[1]))", before=_TRACE),
    "string_comparison": _main("let s = \"\"", "print(s == \"\")", "print(\"ab\" != \"ab\")", "print(\"a\" + \"b\" == \"ab\")"),
    "map_store_inserts": _main("var m = [\"a\": [1]]", "m[\"b\"] = [2, 3]", "print(len(m[\"b\"]))"),
}


def _check_tool():
    return check(link(INTERP_TOOL, stdlib_root=default_stdlib_root()))


class SelfHostedInterpParity(unittest.TestCase):
    _binary: str | None = None
    _tmp: "tempfile.TemporaryDirectory | None" = None

    @classmethod
    def setUpClass(cls) -> None:
        if not CAN_BUILD_NATIVE:
            return
        from myla.compiler import build

        # Build the Myla interpreter to a native binary when we can, so the gate
        # also exercises codegen parity of the toolchain. The x86 backend does
        # not yet support every construct `interp.my` uses, so fall back to the
        # interpreter rather than failing the v0.8 *interpreter* gate on a
        # codegen gap. Once codegen catches up this path upgrades automatically.
        tmp = tempfile.TemporaryDirectory()
        binary = os.path.join(tmp.name, "interp_tool")
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

    def _myla_run_full(self, path: str) -> tuple[str, str, int]:
        proc = subprocess.run(
            [self._binary, path, default_stdlib_root()], capture_output=True, text=True
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
                    self.assertEqual(self._myla_run_full(path), _cli_oracle(path))

    def _myla_run(self, path: str) -> tuple[str, int]:
        argv = [path, default_stdlib_root()]
        if self._binary is not None:
            proc = subprocess.run(
                [self._binary, *argv], capture_output=True, text=True
            )
            return proc.stdout, proc.returncode
        # Interpreter fallback (no native toolchain on this host): run the
        # interpreter source through the Python interpreter, with the example
        # path as argv[1] (what `interp_main` reads).
        out = io.StringIO()
        code = Interpreter(
            _check_tool(), out, argv=["interp_tool", *argv]
        ).run()
        return out.getvalue(), code

    def test_corpus_run_parity(self) -> None:
        checked = 0
        for path in _corpus():
            rel = os.path.relpath(path, _REPO)
            with self.subTest(file=rel):
                self.assertEqual(self._myla_run(path), _oracle(path))
                checked += 1
        # Guard against the corpus silently going empty.
        self.assertGreater(checked, 20)

    def test_parity_programs_match_the_oracle(self) -> None:
        from .test_compiler_parity import PROGRAMS
        from .test_selfhost_codegen import PARITY_PROGRAMS

        with tempfile.TemporaryDirectory() as tmp:
            for name in PARITY_PROGRAMS:
                with self.subTest(program=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(PROGRAMS[name])
                    self.assertEqual(self._myla_run(path), _oracle(path))

    def test_module_programs_match_the_oracle(self) -> None:
        from .test_selfhost_codegen import MODULE_PROJECTS, _write_project

        stdlib = default_stdlib_root()
        entries = {"examples/modules": os.path.join(_REPO, "examples", "modules", "main.my")}
        with tempfile.TemporaryDirectory() as tmp:
            for name, files in MODULE_PROJECTS.items():
                entries[name] = _write_project(os.path.join(tmp, name), files)
            for name, entry in entries.items():
                with self.subTest(program=name):
                    out = io.StringIO()
                    checker = check(link(entry, stdlib_root=stdlib))
                    code = Interpreter(checker, out, argv=[entry]).run()
                    self.assertEqual(self._myla_run(entry), (out.getvalue(), code))


if __name__ == "__main__":
    unittest.main()
