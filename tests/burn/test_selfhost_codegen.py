"""Differential burn test for the self-hosted code generator (self-hosting v0.9).

`selfhost/codegen.my` is the Myla-written x86-64 backend and
`selfhost/gen_main.my` the thin driver: it reads a single-file program, lexes +
parses + type-checks it (prepending the same `Option`/`Result`/`get` prelude the
Python `run` injects), generates GAS assembly, and writes that assembly to
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

Scope. The gate covers the single-file top-level examples; the import-driven
multi-file packages under `examples/<pkg>/` need a module loader the self-hosted
`gen_main` does not have (same boundary as the interpreter/checker gates).
`floats.my` is included since the self-hosted backend has floats (MYLA-29).
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
# floats (MYLA-29).
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
    "STRESS_SB_SRC": "0",
    "STRESS_CLOSURE_SRC": "0",
    "STRESS_PARTIAL_SRC": "0",
    "STRESS_TRAIT_DISPATCH_SRC": "600000",
    "STRESS_FRAGMENTED_FREE_SRC": "38000",
}
PEAK_LIMIT_MB = 30

# A child's peak RSS counts its parent's memory at fork time, so the program
# is started from this minimal helper (a few MB) rather than from the test
# process, and the helper reports the program's exit code and peak (KB).
_MEASURE = (
    "import os, sys\n"
    "pid = os.posix_spawn(sys.argv[1], [sys.argv[1]], os.environ)\n"
    "_, status, usage = os.wait4(pid, 0)\n"
    "sys.stderr.write(f'{os.waitstatus_to_exitcode(status)} {usage.ru_maxrss}\\n')\n"
)


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

    def _emit_asm(self, path: str) -> str:
        """Assembly for `path`, produced by the self-hosted backend."""
        if self._binary is not None:
            proc = subprocess.run(
                [self._binary, path], capture_output=True, text=True
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
            _check_tool(), out, argv=["gen_tool", path]
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
