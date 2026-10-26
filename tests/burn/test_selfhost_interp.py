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
