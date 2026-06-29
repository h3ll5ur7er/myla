"""Differential burn test for the self-hosted parser (self-hosting v0.6b).

`selfhost/parser.my` is the Myla-written parser; `selfhost/parse_main.my` lexes
+ parses a file and prints the canonical AST dump (`canon.canonical_ast`). This
test asserts that, for every source file in the shared corpus, that dump is
byte-for-byte identical to the Python oracle's (`myla parse --canonical`). That
is the v0.6b structural-AST gate from docs/self-hosting.md §5.

As with the lexer gate, the Myla parser runs as a *native binary* when the host
can build one (which also checks interpreter/compiler parity of the toolchain
that built it); otherwise it falls back to the interpreter.
"""
from __future__ import annotations

import glob
import io
import os
import subprocess
import tempfile
import unittest

from myla.canon import canonical_ast
from myla.errors import MylaError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.loader import default_stdlib_root, link
from myla.parser import parse

from ._native import CAN_BUILD_NATIVE

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
PARSE_TOOL = os.path.join(_REPO, "selfhost", "parse_main.my")


def _corpus() -> list[str]:
    """Every .my source we expect to parse: the examples (incl. multi-file
    packages), the error corpus, the bundled stdlib, and the self-hosted
    compiler's own sources."""
    pats = [
        os.path.join(_REPO, "examples", "*.my"),
        os.path.join(_REPO, "examples", "**", "*.my"),
        os.path.join(_REPO, "examples", "errors", "*.my"),
        os.path.join(_REPO, "src", "myla", "std", "*.my"),
        os.path.join(_REPO, "selfhost", "*.my"),
    ]
    files: set[str] = set()
    for p in pats:
        files.update(glob.glob(p, recursive=True))
    return sorted(files)


def _oracle(path: str) -> str | None:
    """Canonical AST dump from the Python parser, or None if the file does not
    parse cleanly (the differential gate compares only successful parses)."""
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    try:
        return canonical_ast(parse(tokenize(source)))
    except MylaError:
        return None


def _check_file(path: str):
    return link(path, stdlib_root=default_stdlib_root())


class SelfHostedParserParity(unittest.TestCase):
    _binary: str | None = None
    _tmp: tempfile.TemporaryDirectory | None = None

    @classmethod
    def setUpClass(cls) -> None:
        if not CAN_BUILD_NATIVE:
            return
        from myla.compiler import build
        from myla.types import check

        cls._tmp = tempfile.TemporaryDirectory()
        cls._binary = os.path.join(cls._tmp.name, "parse_tool")
        build(check(_check_file(PARSE_TOOL)), cls._binary)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._tmp is not None:
            cls._tmp.cleanup()

    def _myla_parse(self, path: str) -> str:
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
            check(_check_file(PARSE_TOOL)), out, argv=["parse_tool", path]
        ).run()
        return out.getvalue().rstrip("\n")

    def test_corpus_ast_parity(self) -> None:
        checked = 0
        for path in _corpus():
            expected = _oracle(path)
            if expected is None:
                continue  # parse-error file: not part of the AST-parity gate
            with self.subTest(file=os.path.relpath(path, _REPO)):
                actual = self._myla_parse(path)
                self.assertEqual(actual, expected)
                checked += 1
        # Guard against the corpus silently going empty.
        self.assertGreater(checked, 25)


if __name__ == "__main__":
    unittest.main()
