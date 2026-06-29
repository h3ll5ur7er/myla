"""Differential burn test for the self-hosted lexer (self-hosting v0.6a).

`selfhost/lexer_tool.my` is the Myla-written lexer. This test asserts that, for
every source file in the shared corpus, its canonical token dump is byte-for-byte
identical to the Python oracle's (`myla tokenize --canonical`, i.e.
`canon.canonical_tokens`). That is the v0.6a differential gate from
docs/self-hosting.md §5.

The Myla lexer is exercised as a *native binary* when the host can build one
(x86-64 Linux with `as`/`ld`), which also checks interpreter/compiler parity of
the toolchain that built it; otherwise it falls back to the interpreter.
"""
from __future__ import annotations

import glob
import io
import os
import subprocess
import tempfile
import unittest

from myla.canon import canonical_tokens
from myla.errors import MylaError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.loader import default_stdlib_root, link

from ._native import CAN_BUILD_NATIVE

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
LEXER_TOOL = os.path.join(_REPO, "selfhost", "lex_main.my")


def _corpus() -> list[str]:
    """Every .my source we expect the lexer to handle: the examples, the error
    corpus, the bundled stdlib, and the self-hosted compiler's own sources."""
    pats = [
        os.path.join(_REPO, "examples", "*.my"),
        os.path.join(_REPO, "examples", "errors", "*.my"),
        os.path.join(_REPO, "src", "myla", "std", "*.my"),
        os.path.join(_REPO, "selfhost", "*.my"),
    ]
    files: list[str] = []
    for p in pats:
        files.extend(sorted(glob.glob(p)))
    return files


def _oracle(path: str) -> str | None:
    """Canonical token dump from the Python lexer, or None if the file does not
    lex cleanly (those are exercised elsewhere; the differential gate compares
    only successful token streams)."""
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    try:
        return canonical_tokens(tokenize(source))
    except MylaError:
        return None


def _check_file(path: str):
    return link(path, stdlib_root=default_stdlib_root())


class SelfHostedLexerParity(unittest.TestCase):
    _binary: str | None = None
    _tmp: tempfile.TemporaryDirectory | None = None

    @classmethod
    def setUpClass(cls) -> None:
        if not CAN_BUILD_NATIVE:
            return
        from myla.compiler import build
        from myla.types import check

        cls._tmp = tempfile.TemporaryDirectory()
        cls._binary = os.path.join(cls._tmp.name, "lexer_tool")
        build(check(_check_file(LEXER_TOOL)), cls._binary)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._tmp is not None:
            cls._tmp.cleanup()

    def _myla_lex(self, path: str) -> str:
        if self._binary is not None:
            proc = subprocess.run(
                [self._binary, path], capture_output=True, text=True
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return proc.stdout.rstrip("\n")
        # Interpreter fallback (no native toolchain on this host).
        from myla.types import check

        out = io.StringIO()
        Interpreter(
            check(_check_file(LEXER_TOOL)), out, argv=["lexer_tool", path]
        ).run()
        return out.getvalue().rstrip("\n")

    def test_corpus_token_parity(self) -> None:
        checked = 0
        for path in _corpus():
            expected = _oracle(path)
            if expected is None:
                continue  # lex-error file: not part of the token-parity gate
            with self.subTest(file=os.path.relpath(path, _REPO)):
                actual = self._myla_lex(path)
                self.assertEqual(actual, expected)
                checked += 1
        # Guard against the corpus silently going empty.
        self.assertGreater(checked, 25)


if __name__ == "__main__":
    unittest.main()
