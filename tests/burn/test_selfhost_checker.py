"""Differential burn test for the self-hosted type checker (self-hosting v0.7).

`selfhost/checker.my` is the Myla-written type checker; `selfhost/check_main.my`
lexes + parses + type-checks a single-file program and prints the stable
accept/reject + diagnostic-position line (`ok`, else `err <line> <col> type`),
the same canonical contract as `myla check --canonical`. This test asserts that,
for every single-file source in the shared corpus, that line is identical to the
Python oracle's. That is the v0.7 checker-parity gate from docs/self-hosting.md.

As with the lexer/parser gates, the Myla checker runs as a *native binary* when
the host can build one (which also exercises interpreter/compiler parity of the
toolchain that built it); otherwise it falls back to the interpreter.

The gate covers single-file programs that lex + parse cleanly and do not import
other modules (the self-hosted `check_main` has no module loader; it injects only
the `Option`/`Result`/`get` prelude, matching a no-import `myla check`). Files
that fail to lex/parse, or that use `import`, are excluded — they belong to the
lexer/parser gates or the runtime corpus, not the checker-parity gate.
"""
from __future__ import annotations

import glob
import io
import os
import subprocess
import tempfile
import unittest

from myla.ast import ImportDecl
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
CHECK_TOOL = os.path.join(_REPO, "selfhost", "check_main.my")


def _corpus() -> list[str]:
    """Every single-file .my source the checker gate covers: the top-level
    examples and the error corpus. (Multi-file example packages and the stdlib
    are import-driven; they are filtered out by `_oracle` below.)"""
    pats = [
        os.path.join(_REPO, "examples", "*.my"),
        os.path.join(_REPO, "examples", "errors", "*.my"),
    ]
    files: set[str] = set()
    for p in pats:
        files.update(glob.glob(p))
    return sorted(files)


def _canonical(err: MylaError) -> str:
    line = "-" if err.line is None else str(err.line)
    col = "-" if err.column is None else str(err.column)
    return f"err {line} {col} {err.kind.split()[0]}"


def _oracle(path: str) -> str | None:
    """Canonical accept/reject line from the Python toolchain, or None if the
    file is not part of the checker-parity gate (does not lex/parse cleanly, uses
    module imports, or rejects with a non-`type` diagnostic class)."""
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    try:
        program = parse(tokenize(source))
    except MylaError:
        return None  # lex/parse-error file: not part of the checker gate
    if any(isinstance(d, ImportDecl) for d in program.decls):
        return None  # import-driven: the self-hosted check_main has no loader
    try:
        check(link(path, stdlib_root=default_stdlib_root()))
    except MylaError as err:
        kind = err.kind.split()[0]
        if kind != "type":
            return None  # only the `type` diagnostic class is in scope
        return _canonical(err)
    return "ok"


def _check_file(path: str):
    return link(path, stdlib_root=default_stdlib_root())


class SelfHostedCheckerParity(unittest.TestCase):
    _binary: str | None = None
    _tmp: tempfile.TemporaryDirectory | None = None

    @classmethod
    def setUpClass(cls) -> None:
        if not CAN_BUILD_NATIVE:
            return
        from myla.compiler import build

        # Build the Myla checker to a native binary when we can, so the gate also
        # exercises codegen parity of the toolchain. The x86 backend does not yet
        # support every construct `checker.my` uses (e.g. assigning a heap-owning
        # value to a struct field — that's v0.9a codegen work), so fall back to
        # the interpreter rather than failing the v0.7 *checker* gate on a codegen
        # gap. Once codegen catches up this path upgrades to native automatically.
        tmp = tempfile.TemporaryDirectory()
        binary = os.path.join(tmp.name, "check_tool")
        try:
            build(check(_check_file(CHECK_TOOL)), binary)
        except Exception:
            tmp.cleanup()
            return
        cls._tmp = tmp
        cls._binary = binary

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._tmp is not None:
            cls._tmp.cleanup()

    def _myla_check(self, path: str) -> str:
        if self._binary is not None:
            proc = subprocess.run(
                [self._binary, path], capture_output=True, text=True
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return proc.stdout.rstrip("\n")
        # Interpreter fallback (no native toolchain on this host).
        out = io.StringIO()
        Interpreter(
            check(_check_file(CHECK_TOOL)), out, argv=["check_tool", path]
        ).run()
        return out.getvalue().rstrip("\n")

    def test_corpus_check_parity(self) -> None:
        checked = 0
        for path in _corpus():
            expected = _oracle(path)
            if expected is None:
                continue  # not part of the checker-parity gate
            with self.subTest(file=os.path.relpath(path, _REPO)):
                actual = self._myla_check(path)
                self.assertEqual(actual, expected)
                checked += 1
        # Guard against the corpus silently going empty.
        self.assertGreater(checked, 60)


if __name__ == "__main__":
    unittest.main()
