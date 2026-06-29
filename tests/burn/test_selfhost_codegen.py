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
`floats.my` is excluded: the self-hosted AST records only a float literal's
*suffix*, not its digits (`FloatLit(Option<str>)`), so float values cannot be
reconstructed yet — a parser/AST limitation tracked separately, not a codegen
gap.
"""
from __future__ import annotations

import glob
import io
import os
import subprocess
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
EXCLUDED = {"floats.my"}


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
                [bin_path], capture_output=True, text=True
            )
            return proc.stdout, proc.returncode

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


if __name__ == "__main__":
    unittest.main()
