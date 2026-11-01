"""Differential burn test for the self-hosted parser (self-hosting v0.6b).

`selfhost/parser.my` is the Myla-written parser; `selfhost/parse_main.my` lexes
+ parses a file and prints the canonical AST dump (`canon.canonical_ast`). This
test asserts that, for every source file in the shared corpus, that dump is
byte-for-byte identical to the Python oracle's (`myla parse --canonical`). That
is the v0.6b structural-AST gate from docs/Development/Testing.md. For a source
with syntax errors, both report every error the parser recovers from, in order
(MYLA-65, D80). The oracle's dumps are the retired Python parser's, recorded
(`tests/burn/_golden.py`, MYLA-219).

As with the lexer gate, the Myla parser runs as a *native binary* built by the
self-hosted compiler, so the test needs a host that can build one (the
interpreter fallback went with the Python toolchain).
"""
from __future__ import annotations

import glob
import os
import random
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
    # nesting past MAX_NESTING (256) in each kind of construct (MYLA-182)
    "nested_unary_operators": "fun main() {\n    let x = " + "-" * 300 + "1\n}\n",
    "nested_types": "fun f(x: " + "[" * 300 + "int" + "]" * 300 + ") {\n}\n",
    "nested_blocks": "fun main() {\n" + "    if true {\n" * 300 + "    }\n" * 300 + "}\n",
    "nested_patterns": "fun f(x: int) {\n    match x {\n        " + "(" * 300 + "1" + ",)" * 300 + " => {},\n    }\n}\n",
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
    # strings and f-strings take the char escapes (MYLA-86)
    "string_unicode_no_brace": 'fun main() {\n    let s = "\\u0041"\n}\n',
    "string_unicode_hex_digit": 'fun main() {\n    let s = "\\u{4G}"\n}\n',
    "string_unicode_unterminated": 'let s = "\\u{41',
    "string_unicode_empty": 'fun main() {\n    let s = "a\\u{}"\n}\n',
    "string_unicode_surrogate": 'fun main() {\n    let s = "\\u{DFFF}"\n}\n',
    "string_unicode_too_big": 'fun main() {\n    let s = "\\u{110000}"\n}\n',
    "fstring_unicode_surrogate": 'fun main() {\n    let s = f"{1}\\u{D800}"\n}\n',
    "fstring_unicode_no_brace": 'fun main() {\n    let s = f"\\u41{1}"\n}\n',
    # identifiers are Unicode's XID (MYLA-84): these may continue one, not start it
    "ident_middle_dot_start": "fun main() {\n    let \u00b7a = 1\n}\n",
    "ident_arabic_digit_start": "fun main() {\n    let \u0661 = 1\n}\n",
    "ident_combining_start": "fun main() {\n    let \u0301a = 1\n}\n",
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
    # several errors: the parser resumes at the next statement, member or
    # declaration (MYLA-65, D80)
    "several_statements": "fun main() {\n    let = 1\n    let y = 2\n    y = = 3\n}\nfun g() {\n    print(1 +)\n}\n",
    "several_on_a_line": "fun main() {\n    let x = = = 1; let = 2\n}\n",
    "header_then_body": "fun f(a int) -> int {\n    return a\n}\nfun main() {\n    let = 1\n}\n",
    "statement_spanning_lines": "fun main() {\n    print(f(1 +,\n        2))\n    let = 1\n}\n",
    "unclosed_parenthesis": "fun main() {\n    let x = (1 + 2\n    let y = = 3\n}\n",
    "missing_brace": "fun f() {\n    if true {\n        let x = 1\n}\nfun g() {\n    let = 2\n}\n",
    "missing_brace_after_an_error": "fun f() {\n    let = 1\n    if true {\n        print(1)\n\nfun g() {\n    let = 2\n}\n",
    "missing_brace_in_a_method": ("struct S { a: int }\nimpl S {\n    fun f(self) {\n        if true {\n    }\n"
                                  "    fun g(self) {\n        let = 1\n    }\n}\nfun main() {\n    let = 2\n}\n"),
    "impl_members": ("struct S { a: int }\nimpl S {\n    fun f(self) -> int {\n        return = 1\n    }\n"
                     "    let x = 1\n    fun g(self) -> int {\n        return self.a +\n    }\n}\n"
                     "fun main() {\n    let = 1\n}\n"),
    "trait_members": "trait T {\n    fun f(self) -> \n    let x = 1\n    fun g(x: int)\n}\nfun main() {\n    let = 1\n}\n",
    "struct_body": "struct P {\n    x int,\n    y: int,\n}\nfun main() {\n    let = 1\n}\n",
    "top_level_statements": "let x = 1\nx = 2\nfun main() {}\nprint(x)\n",
    "nested_blocks": ("fun main() {\n    while true {\n        if x { y = = 1 } else { z = = 2 }\n"
                      "        for i in 0..+ {\n            break\n        }\n    }\n    let = 3\n}\n"),
    "lambda_and_match_bodies": ("fun main() {\n    let f = (x: int) => {\n        return = x\n    }\n"
                                "    let y = match 1 {\n        1 => { let = 2 }\n        _ => 3\n    }\n}\n"),
    "stray_closers": "fun main() {\n    let x = 1 ) ]\n    let = 2\n}\n}\nfun g() {\n    let = 3\n}\n",
    "too_many": "fun main() {\n" + "    let = 1\n" * 25 + "}\n",
    # concurrency (D89, MYLA-135)
    "async_before_non_function_type": "fun f(x: async int) {\n}\n",
    "async_tuple_type": "fun f(x: async (int, int)) {\n}\n",
    "async_without_lambda": "fun main() {\n    let f = async (1 + 2)\n}\n",
    "async_let_without_name": "async fun f() {\n    async let = g()\n}\n",
    "async_let_without_value": "async fun f() {\n    async let x: int\n}\n",
    "actor_without_name": "actor {\n    n: int\n}\n",
    "async_alone": "async struct S { a: int }\n",
    "async_method_in_body": "struct S { a: int }\nimpl S {\n    async let x = 1\n}\n",
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


# Every construct of concurrency (D89, MYLA-135); the test parses it whole and
# each prefix of it.
CONCURRENCY = (
    "import std.task\n"
    "actor Counter {\n    count: int,\n}\n"
    "impl Counter {\n"
    "    fun increment(var self) -> int {\n        self.count = self.count + 1\n        return self.count\n    }\n"
    "    async fun slow(self, f: async (int) -> int) -> int {\n        return await f(self.count)\n    }\n"
    "}\n"
    "trait T {\n    async fun t(self) -> int\n}\n"
    "pub async fun fetch<U>(n: int, u: U) -> int {\n    return n * 10\n}\n"
    "#main\n"
    "async fun main() {\n"
    "    let c = Counter { count: 0 }\n"
    "    async let a = fetch(1, true)\n"
    "    async let b: int = await fetch(2, 'x') + 1\n"
    "    let f: async () -> int = async () => await a\n"
    "    let g = async (n: int) => {\n        return await c.slow(async (m: int) => m)\n    }\n"
    "    print(await -await b + await await_this(await a))\n"
    "    var async_ = await (await c).increment()\n"
    "}\n"
)

# Files whose every prefix (cut at each line end and in the middle of each
# line) is parsed by both front ends: they must agree, and the self-hosted one
# must not loop.
TRUNCATED = ["closures.my", "enums.my", "interpolation.my", "traits.my", "generics.my", "chars.my"]

# Garbled copies of every example, with a few lines broken in one of these
# ways: both parsers must recover alike (MYLA-65, D80).
GARBLINGS = [
    lambda line: line + " )",
    lambda line: line.replace("(", "", 1),
    lambda line: line.replace(")", "", 1),
    lambda line: line.replace("=", "= =", 1),
    lambda line: line.replace("{", "", 1),
    lambda line: line.replace("}", "", 1),
    lambda line: line.replace(":", "", 1),
    lambda line: line.replace(",", ",,", 1),
    lambda line: "fun " + line,
    lambda line: line + " {",
]


def _garbled(source: str, rng: random.Random, n: int) -> str:
    """`source` with `n` of its lines garbled (GARBLINGS)."""
    lines = source.split("\n")
    for i in rng.sample(range(len(lines)), min(n, len(lines))):
        lines[i] = rng.choice(GARBLINGS)(lines[i])
    return "\n".join(lines)


@golden("selfhost_parser.ast")
def _canonical(source: str) -> str:
    """Canonical AST dump from the Python parser, or its errors as
    `err <line> <col> <span> <kind>: <message>` lines (what `parse_main`
    prints): the range a diagnostic underlines must agree too (MYLA-65)."""
    from myla.canon import canonical_ast, canonical_errors
    from myla.errors import MylaError
    from myla.lexer import tokenize
    from myla.parser import parse
    try:
        return canonical_ast(parse(tokenize(source)))
    except MylaError as err:
        return canonical_errors(err)


def _oracle(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    # skipped when the file changed after the retirement (selfhost/, tools/, std)
    return answer_for_file(path, lambda: _canonical(source))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class SelfHostedParserParity(unittest.TestCase):
    _binary: str | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._binary = selfhost_tool("parse_main")

    def _myla_parse_source(self, source: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".my", encoding="utf-8", delete=False) as fh:
            fh.write(source)
        try:
            return self._myla_parse(fh.name)
        finally:
            os.unlink(fh.name)

    def _myla_parse(self, path: str) -> str:
        proc = subprocess.run(
            [self._binary, path], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.rstrip("\n")

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

    def test_concurrency_matches_the_oracle(self) -> None:
        expected = _canonical(CONCURRENCY)
        self.assertFalse(expected.startswith("err "), expected)
        self.assertEqual(self._myla_parse_source(CONCURRENCY), expected)
        cuts = set()
        pos = 0
        for line in CONCURRENCY.splitlines(keepends=True):
            cuts.add(pos + len(line) // 2)
            pos += len(line)
            cuts.add(pos)
        for cut in sorted(cuts):
            prefix = CONCURRENCY[:cut]
            with self.subTest(cut=cut):
                self.assertEqual(self._myla_parse_source(prefix), _canonical(prefix))

    def test_garbled_sources_match_the_oracle(self) -> None:
        several = 0
        for path in sorted(glob.glob(os.path.join(_REPO, "examples", "*.my"))):
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            for seed in range(4):
                garbled = _garbled(source, random.Random(f"{os.path.basename(path)}/{seed}"), 1 + 2 * seed)
                with self.subTest(file=os.path.basename(path), seed=seed):
                    expected = _canonical(garbled)
                    self.assertEqual(self._myla_parse_source(garbled), expected)
                    several += expected.count("\nerr ") > 0
        # most garbled sources have several errors
        self.assertGreater(several, 50)

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
