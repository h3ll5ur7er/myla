"""Differential burn test for the self-hosted parser (self-hosting v0.6b).

`selfhost/parser.my` is the Myla-written parser; `selfhost/parse_main.my` lexes
+ parses a file and prints the canonical AST dump (`canon.canonical_ast`). This
test asserts that, for every source file in the shared corpus, that dump is
byte-for-byte identical to the Python oracle's (`myla parse --canonical`). That
is the v0.6b structural-AST gate from docs/Development/Testing.md

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
from ._tools import selfhost_tool

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


# Snippets for every lexer and parser error the corpus lacks (MYLA-28): the
# self-hosted front end must report Python's message at Python's position.
SYNTAX_ERRORS = {
    "block_comment": "fun main() {}\n/* never closed\n",
    "separator_doubled": "fun main() {\n    let x = 1__0\n}\n",
    "separator_leading": "fun main() {\n    let x = 0x_1\n}\n",
    "separator_trailing": "fun main() {\n    let x = 10_\n}\n",
    "int_suffix": "fun main() {\n    let x = 5i7\n}\n",
    "int_trailing_letter": "fun main() {\n    let x = 5x\n}\n",
    "no_digits_after_prefix": "fun main() {\n    let x = 0b\n}\n",
    "float_suffix": "fun main() {\n    let x = 1.5f16\n}\n",
    "float_trailing_letter": "fun main() {\n    let x = 1.5q\n}\n",
    "string_newline": 'fun main() {\n    let s = "abc\n}\n',
    "string_backslash_at_end": 'let s = "ab\\',
    "string_escape": 'fun main() {\n    let s = "a\\qb"\n}\n',
    "unicode_no_brace": "fun main() {\n    let c = '\\u0041'\n}\n",
    "unicode_hex_digit": "fun main() {\n    let c = '\\u{4G}'\n}\n",
    "unicode_unterminated": "let c = '\\u{41",
    "unicode_empty": "fun main() {\n    let c = '\\u{}'\n}\n",
    "unicode_surrogate": "fun main() {\n    let c = '\\u{D800}'\n}\n",
    "unicode_too_big": "fun main() {\n    let c = '\\u{110000}'\n}\n",
    "char_empty": "fun main() {\n    let c = ''\n}\n",
    "char_backslash_at_end": "let c = '\\",
    "char_escape": "fun main() {\n    let c = '\\q'\n}\n",
    "char_two": "fun main() {\n    let c = 'ab'\n}\n",
    "unexpected_char": "fun main() {\n    let x = 1 @ 2\n}\n",
    "unexpected_multibyte_char": "fun main() {\n    let x = 1 \u20ac 2\n}\n",
    "fstring_newline": 'fun main() {\n    let s = f"abc\n}\n',
    "fstring_single_close": 'fun main() {\n    let s = f"a}b"\n}\n',
    "fstring_backslash_at_end": 'let s = f"a\\',
    "fstring_escape": 'fun main() {\n    let s = f"a\\qb"\n}\n',
    "fstring_open_hole": 'fun main() {\n    let s = f"a{x"\n}\n',
    "fstring_blank_hole": 'fun main() {\n    let s = f"a{  }b"\n}\n',
    "fstring_hole_string": 'fun main() {\n    let s = f"a{"bc}"\n}\n',
    "fstring_hole_lex_error": 'fun main() {\n    let s = f"a{1x}"\n}\n',
    "expect": "fun main( {\n}\n",
    "end_of_statement": "fun main() {\n    let x = 1 let y = 2\n}\n",
    "impl_attribute": "struct S { a: int }\n#test\nimpl S {\n}\n",
    "impl_pub": "struct S { a: int }\npub impl S {\n}\n",
    "import_attribute": "#test\nimport foo\n",
    "pub_import_without_alias": "pub import foo\n",
    "empty_type_params": "fun f<>() {\n}\n",
    "bounds_on_alias": "type A<T: Eq> = int\n",
    "impl_trait_not_a_name": "struct S { a: int }\nimpl [int] for S {\n}\n",
    "impl_body_not_fun": "struct S { a: int }\nimpl S {\n    let x = 1\n}\n",
    "trait_body_not_fun": "trait T {\n    let x = 1\n}\n",
    "expected_type": "fun f(x: 1) {\n}\n",
    "unit_type": "fun f(x: ()) {\n}\n",
    "struct_fields_on_one_line": "struct S { a: int b: int }\n",
    "binding_name": "fun main() {\n    let (1, 2) = (1, 2)\n}\n",
    "expected_expression": "fun main() {\n    let x = \n}\n",
    "expected_pattern": "fun main() {\n    let x = match 1 {\n        + => 1,\n    }\n}\n",
    # `;` separates statements and declarations, and nothing else (MYLA-76)
    "semicolon_in_arguments": "fun main() { f(1; 2) }\n",
    "semicolon_in_list": "fun main() { let x = [1; 2] }\n",
    "semicolon_between_fields": "struct S { a: int; b: int }\n",
    "semicolon_as_expression": "fun main() { let x = ; }\n",
    "semicolon_between_arms": "fun main() { match 1 { 1 => 2; _ => 3 } }\n",
    "semicolon_before_else": "fun main() { if true {}; else {} }\n",
    "statements_without_separator": "fun main() {\n    let x = 1 let y = 2\n}\n",
    "declarations_without_separator": "const A: int = 1 const B: int = 2\n",
    # `>=` closing type arguments is split into `>` and `=` (MYLA-15)
    "split_ge_then_missing_value": "fun main() {\n    let x: Option<int>=\n}\n",
    "split_ge_in_a_parameter": "fun f(x: Option<int>= 1) {}\n",
}

# Integer literals of 2^63 and above (MYLA-73): the canonical AST and token
# dumps show their value, which the self-hosted lexer used to wrap.
BIG_LITERALS = (
    "fun main() {\n"
    "    let a = 9223372036854775807\n"
    "    let b = 9223372036854775808\n"
    "    let c = 18446744073709551615u64\n"
    "    let d = 18446744073709551616\n"
    "    let e = 0xFFFF_FFFF_FFFF_FFFF\n"
    "    let f = 0x1_0000_0000_0000_0000\n"
    "    let g = 0b1000000000000000000000000000000000000000000000000000000000000000\n"
    "    let h = 340282366920938463463374607431768211456\n"
    "    let i = 000000000000000000000000000000000000000000042\n"
    "    let m = x & 9223372036854775808\n"
    "}\n"
)


# Files whose every prefix (cut at each line end and in the middle of each
# line) is parsed by both front ends: they must agree, and the self-hosted one
# must stop after its first error instead of looping.
TRUNCATED = ["closures.my", "enums.my", "interpolation.my", "traits.my", "generics.my", "chars.my"]


def _canonical(source: str) -> str:
    """Canonical AST dump from the Python parser, or its error as
    `err <line> <col> <kind>: <message>` (what `parse_main` prints)."""
    try:
        return canonical_ast(parse(tokenize(source)))
    except MylaError as err:
        return f"err {err.line} {err.column} {err.kind.split()[0]}: {err.message}"


def _oracle(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return _canonical(fh.read())


def _check_file(path: str):
    return link(path, stdlib_root=default_stdlib_root())


class SelfHostedParserParity(unittest.TestCase):
    _binary: str | None = None

    @classmethod
    def setUpClass(cls) -> None:
        if not CAN_BUILD_NATIVE:
            return
        cls._binary = selfhost_tool("parse_main")

    def _myla_parse_source(self, source: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".my", encoding="utf-8", delete=False) as fh:
            fh.write(source)
        try:
            return self._myla_parse(fh.name)
        finally:
            os.unlink(fh.name)

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
        checked = errors = 0
        for path in _corpus():
            expected = _oracle(path)
            with self.subTest(file=os.path.relpath(path, _REPO)):
                actual = self._myla_parse(path)
                self.assertEqual(actual, expected)
                checked += 1
                errors += expected.startswith("err ")
        # Guard against the corpus silently going empty.
        self.assertGreater(checked, 25)
        self.assertGreater(errors, 15)

    def test_syntax_errors_match_the_oracle(self) -> None:
        for name, source in SYNTAX_ERRORS.items():
            with self.subTest(case=name):
                expected = _canonical(source)
                self.assertTrue(expected.startswith("err "), "not an error in Python")
                self.assertEqual(self._myla_parse_source(source), expected)

    def test_big_integer_literals_match_the_oracle(self) -> None:
        self.assertEqual(self._myla_parse_source(BIG_LITERALS), _canonical(BIG_LITERALS))

    def test_truncated_sources_match_the_oracle(self) -> None:
        for name in TRUNCATED:
            with open(os.path.join(_REPO, "examples", name), encoding="utf-8") as fh:
                source = fh.read()
            cuts = set()
            pos = 0
            for line in source.splitlines(keepends=True):
                cuts.add(pos + len(line) // 2)
                pos += len(line)
                cuts.add(pos)
            for cut in sorted(cuts):
                prefix = source[:cut]
                with self.subTest(file=name, cut=cut):
                    self.assertEqual(self._myla_parse_source(prefix), _canonical(prefix))


if __name__ == "__main__":
    unittest.main()
