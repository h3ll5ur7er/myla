"""Differential burn test for the self-hosted lexer (self-hosting v0.6a).

`selfhost/lexer_tool.my` is the Myla-written lexer. This test asserts that, for
every source file in the shared corpus, its canonical token dump is byte-for-byte
identical to the Python oracle's (`myla tokenize --canonical`, i.e.
`canon.canonical_tokens`). That is the v0.6a differential gate from
docs/Development/Testing.md

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
from ._tools import selfhost_tool

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


def _oracle(path: str) -> str:
    """Canonical token dump from the Python lexer, or its error as
    `err <line> <col> lex: <message>` (what `lex_main` prints)."""
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    try:
        return canonical_tokens(tokenize(source))
    except MylaError as err:
        return f"err {err.line} {err.column} {err.kind.split()[0]}: {err.message}"


def _check_file(path: str):
    return link(path, stdlib_root=default_stdlib_root())


class SelfHostedLexerParity(unittest.TestCase):
    _binary: str | None = None

    @classmethod
    def setUpClass(cls) -> None:
        if not CAN_BUILD_NATIVE:
            return
        cls._binary = selfhost_tool("lex_main")

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

    def test_big_integer_literals(self) -> None:
        # the token dump shows the value of literals of 2^63 and above (MYLA-73)
        from .test_selfhost_parser import BIG_LITERALS

        with tempfile.NamedTemporaryFile("w", suffix=".my", encoding="utf-8", delete=False) as fh:
            fh.write(BIG_LITERALS)
        try:
            with open(fh.name, encoding="utf-8") as src:
                expected = canonical_tokens(tokenize(src.read()))
            self.assertEqual(self._myla_lex(fh.name), expected)
        finally:
            os.unlink(fh.name)

    def test_unicode_identifiers_and_escapes(self) -> None:
        # XID identifiers and the escapes strings share with chars (MYLA-84, MYLA-86)
        source = ("fun größe(π: int, x\u0301: int, a\u00b7b: int) -> int {\n"
                  "    let 日本 = \"\\r\\n\\0\\'\\u{41}\\u{1F600}\"\n"
                  "    let s = f\"\\u{7B}{π}\\r\"\n"
                  "    let c = '\\\"'\n"
                  "    return π + Ⅻ + ℘\n"
                  "}\n")
        with tempfile.NamedTemporaryFile("w", suffix=".my", encoding="utf-8", delete=False) as fh:
            fh.write(source)
        try:
            expected = canonical_tokens(tokenize(source))
            self.assertIn("größe", expected)
            self.assertEqual(self._myla_lex(fh.name), expected)
        finally:
            os.unlink(fh.name)

    def test_corpus_token_parity(self) -> None:
        checked = 0
        for path in _corpus():
            expected = _oracle(path)
            with self.subTest(file=os.path.relpath(path, _REPO)):
                actual = self._myla_lex(path)
                self.assertEqual(actual, expected)
                checked += 1
        # Guard against the corpus silently going empty.
        self.assertGreater(checked, 25)


if __name__ == "__main__":
    unittest.main()
