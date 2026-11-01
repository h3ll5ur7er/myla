"""Differential burn test for the self-hosted lexer (self-hosting v0.6a).

`selfhost/lexer_tool.my` is the Myla-written lexer. This test asserts that, for
every source file in the shared corpus, its canonical token dump is byte-for-byte
identical to the Python oracle's (`myla tokenize --canonical`, i.e.
`canon.canonical_tokens`). That is the v0.6a differential gate from
docs/Development/Testing.md. The oracle's dumps are the retired Python lexer's,
recorded (`tests/burn/_golden.py`, MYLA-219).

The Myla lexer runs as a *native binary* built by the self-hosted compiler, so
the test needs a host that can build one (x86-64 Linux with `as`/`ld`). (It
fell back to the Python interpreter elsewhere; the self-hosted interpreter is
itself a native binary, so there is no fallback any more.)
"""
from __future__ import annotations

import glob
import os
import subprocess
import tempfile
import unittest

from ._golden import answer_for_file, golden
from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import selfhost_tool

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)


def _corpus() -> list[str]:
    """Every .my source we expect the lexer to handle: the examples, the error
    corpus, the bundled stdlib, and the self-hosted compiler's own sources."""
    pats = [
        os.path.join(_REPO, "examples", "*.my"),
        os.path.join(_REPO, "examples", "errors", "*.my"),
        os.path.join(_REPO, "lib", "std", "*.my"),
        os.path.join(_REPO, "selfhost", "*.my"),
    ]
    files: list[str] = []
    for p in pats:
        files.extend(sorted(glob.glob(p)))
    return files


@golden("selfhost_lexer.tokens")
def _oracle_source(source: str) -> str:
    """Canonical token dump from the Python lexer (token ends included), or
    its error as `err <line> <col> <span> lex: <message>` (what `lex_main`
    prints): the same tokens and errors, ranges included (MYLA-65)."""
    from myla.canon import canonical_error, canonical_tokens
    from myla.errors import MylaError
    from myla.lexer import tokenize
    try:
        return canonical_tokens(tokenize(source))
    except MylaError as err:
        return canonical_error(err)


@golden("selfhost_lexer.tokens_strict")
def _tokens(source: str) -> str:
    """Canonical token dump from the Python lexer of a source it lexes."""
    from myla.canon import canonical_tokens
    from myla.lexer import tokenize
    return canonical_tokens(tokenize(source))


def _oracle(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    # skipped when the file changed after the retirement (selfhost/, tools/, std)
    return answer_for_file(path, lambda: _oracle_source(source))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class SelfHostedLexerParity(unittest.TestCase):
    _binary: str | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._binary = selfhost_tool("lex_main")

    def _myla_lex(self, path: str) -> str:
        proc = subprocess.run(
            [self._binary, path], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.rstrip("\n")

    def test_big_integer_literals(self) -> None:
        # the token dump shows the value of literals of 2^63 and above (MYLA-73)
        from .test_selfhost_parser import BIG_LITERALS

        with tempfile.NamedTemporaryFile("w", suffix=".my", encoding="utf-8", delete=False) as fh:
            fh.write(BIG_LITERALS)
        try:
            with open(fh.name, encoding="utf-8") as src:
                expected = _tokens(src.read())
            self.assertEqual(self._myla_lex(fh.name), expected)
        finally:
            os.unlink(fh.name)

    def test_a_byte_order_mark_is_skipped(self) -> None:
        # a UTF-8 BOM at the start takes no column; one elsewhere is an error
        # in both lexers (MYLA-178)
        for source in ("\ufefffun main() {\n    print(1)\n}\n", "fun main() {\n    \ufeff\n}\n"):
            with self.subTest(source=source), tempfile.NamedTemporaryFile(
                    "w", suffix=".my", encoding="utf-8", delete=False) as fh:
                fh.write(source)
            try:
                self.assertEqual(self._myla_lex(fh.name), _oracle(fh.name))
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
            expected = _tokens(source)
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
