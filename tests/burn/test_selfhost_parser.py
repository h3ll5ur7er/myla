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
import time
import unittest

from ._golden import NoGolden, answer_for_file, golden, recorded, recorded_examples
from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._continuation import continues_a_line
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
        os.path.join(_REPO, "lib", "std", "*.my"),
        os.path.join(_REPO, "selfhost", "*.my"),
    ]
    files: set[str] = set()
    for p in pats:
        files.update(glob.glob(p, recursive=True))
    # the files as the recordings saw them (rewritten since: MYLA-240)
    return sorted(recorded(f) for f in files)


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
    "impl_pub": "struct S { a: int }\npub impl S {\n}\n",
    "import_attribute": "#test\nimport foo\n",
    "pub_import_without_alias": "pub import foo\n",
    "empty_type_params": "fun f<>() {\n}\n",
    "bounds_on_alias": "type A<T: Eq> = int\n",
    "impl_trait_not_a_name": "struct S { a: int }\nimpl [int] for S {\n}\n",
    "impl_body_not_fun": "struct S { a: int }\nimpl S {\n    let x = 1\n}\n",
    "trait_body_not_fun": "trait T {\n    let x = 1\n}\n",
    "expected_type": "fun f(x: 1) {\n}\n",
    # (`fun f(x: ())` was one; since D138 `()` is the unit type: test_unit_type)
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
    # (`fun f(x: Option<int>= 1)` was one; since D136 the `=` is a default:
    # test_default_params)
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


# Parses that line continuation (D104 (3), MYLA-224) changed from the retired
# Python parser's recording: the line break the error used to point at no
# longer makes a token, so the error names the next one.
SUPERSEDED: dict[str, str] = {
    "split_ge_then_missing_value": "err 3 1 3:1-3:2 parse: expected an expression, found '}'",
    "impl_members": "err 4 16 4:16-4:17 parse: expected an expression, found '='\n"
                    "err 6 5 6:5-6:8 parse: expected a method ('fun ...') in impl block, found 'let'\n"
                    "err 9 5 9:5-9:6 parse: expected an expression, found '}'\n"
                    "err 12 9 12:9-12:10 parse: expected variable name, found '='",
}


# The retired parser's error for a method without a receiver: since D172
# (MYLA-384) a trait's or impl's function may have none, so the parse goes on
# where the recording stopped, and its later errors can differ. Where a
# recording has it, the parse is held to erring as the recording did.
_RECEIVER_ERROR = "a method's first parameter must be 'self' or 'var self'"


def _receiverless(expected: str) -> bool:
    return _RECEIVER_ERROR in expected


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
            # in the file's subtest: a file changed since the retirement skips
            # only itself (the recorded copies sort after lib/ and selfhost/)
            with self.subTest(file=os.path.relpath(path, _REPO)):
                try:
                    expected = _oracle(path)
                except NoGolden:
                    continue    # a file added to the corpus since has no recording: test_error_corpus holds it to the self-hosted CLI
                actual = self._myla_parse(path)
                self.assertEqual(actual, expected)
                checked += 1
                errors += expected.startswith("err ")
        # Guard against the corpus silently going empty.
        self.assertGreater(checked, 25)
        self.assertGreater(errors, 15)

    def test_bodies_read_later_are_the_same(self) -> None:
        # MYLA-359: a file read as an implicit module is (each function's
        # body skipped by the lexer, then lexed and parsed on its own) gives
        # the tokens, with their places, and the tree of the file read
        # whole; `parse_main --lazy` compares them. Every file of the
        # corpus, the error corpus's lex errors included; only
        # parse_several_errors reports its errors in another order (the
        # signatures' first, then the bodies' as they are read). A file of
        # the standard library reads without an error (MYLA-416: one that
        # failed both ways passed as `same 0`).
        bodies = 0
        std = set(glob.glob(os.path.join(_REPO, "lib", "std", "**", "*.my"), recursive=True))
        for path in sorted(set(_corpus()) | std):
            if path.endswith("parse_several_errors.my"):
                continue
            with self.subTest(file=os.path.relpath(path, _REPO)):
                proc = subprocess.run([self._binary, "--lazy", path], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue(proc.stdout.startswith("same "), proc.stdout[:2000])
                if path in std:
                    self.assertNotEqual(proc.stdout.strip(), "same error", path)
                word = proc.stdout.split()[1]
                n = int(word) if word.isdigit() else 0
                # `same 0` is two parses failing alike (MYLA-418), as is
                # `same error` (MYLA-416): a file of the library or the
                # compiler parses and has bodies
                if os.path.relpath(path, _REPO).startswith(("lib" + os.sep, "selfhost" + os.sep)):
                    self.assertGreater(n, 0, proc.stdout[:2000])
                bodies += n
        self.assertGreater(bodies, 5000)

    def test_a_long_run_of_comparisons_parses_in_linear_time(self) -> None:
        # MYLA-416 (D186): the scan for explicit type arguments followed
        # `x < y, x < y, …` from every `<` to the end (32,000 in a list: 25 s
        # in the review, 13 s here); a comma ends it in a literal's element,
        # and a budget of tokens in a call's arguments
        n = 32000
        with tempfile.TemporaryDirectory() as tmp:
            for name, line in [("list", "    let t = [" + ", ".join(["x < y"] * n) + "]\n"),
                               ("call", "    let t = f(" + ", ".join(["x < y"] * n) + ")\n")]:
                path = os.path.join(tmp, name + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("fun main() {\n    let x = 1\n    let y = 2\n" + line + "}\n")
                start = time.monotonic()
                proc = subprocess.run([self._binary, path], capture_output=True, text=True)
                took = time.monotonic() - start
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.count('(binary "<" (name "x") (name "y"))'), n, name)
                self.assertLess(took, 5.0, name)

    def test_type_arguments_have_no_budget_of_tokens(self) -> None:
        # MYLA-545: the scan looked at 128 tokens, so a tuple of 63 types was
        # a type argument and one of 64 a comparison (`generic function 'mk'
        # cannot be used as a value`), and so was a type 43 deep
        myla = selfhost_tool("main")
        wide = "(" + ", ".join(["int"] * 200) + ")"
        deep = "B<" * 60 + "int" + ">" * 60
        with tempfile.TemporaryDirectory() as tmp:
            for name, targ in (("wide", wide), ("deep", deep)):
                path = os.path.join(tmp, name + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("struct B<T> { v: [T] }\nfun mk<T>(n: int) -> int { return n }\n"
                             f"fun main() {{\n    print(mk<{targ}>(1))\n}}\n")
                proc = subprocess.run([myla, "run", path], capture_output=True, text=True, timeout=120)
                self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("1\n", "", 0), name)

    def test_a_long_chain_of_operators_is_a_parse_error(self) -> None:
        # MYLA-545: `x < y && x < y && …` 16,000 long overflowed the
        # checker's stack (its tree is as deep as the chain); 8,192
        # operators in an expression parse, one more is a parse error there
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            for operands, op in ((4096, "&&"), (16000, "&&"), (8193, "+"), (16000, "+"), (8193, ".abs()")):
                if op == "&&":
                    text = " &&\n        ".join(["x < y"] * operands)    # two operators an operand
                elif op == "+":
                    text = " +\n        ".join(["x"] * operands)
                else:
                    text = "x" + ".abs()" * ((operands - 1) // 2)    # a field and a call each
                path = os.path.join(tmp, f"chain_{operands}_{len(op)}.my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("fun main() {\n    let x = 1\n    let y = 2\n    let t = " + text + "\n    print(t)\n}\n")
                ok = operands <= 8193
                for cmd in ("check", "run"):
                    with self.subTest(operands=operands, op=op, cmd=cmd):
                        proc = subprocess.run([myla, cmd, path], capture_output=True, text=True, timeout=300)
                        if ok:
                            want = {"&&": "true\n", "+": f"{operands}\n", ".abs()": "1\n"}[op]
                            self.assertEqual((proc.stdout, proc.stderr), ("ok\n" if cmd == "check" else want, ""))
                        else:
                            # the 8,193rd: with `&&`, the `&&` after the 4,096th
                            # operand (its two operators counted), with `+` the
                            # `+` after the 8,193rd
                            line = 4099 if op == "&&" else 8196
                            self.assertEqual(proc.returncode, 1)
                            self.assertTrue(proc.stderr.startswith(
                                "parse error: more than 8192 operators, calls and fields in one expression: split it with a 'let'\n"
                                f"  --> {path}:{line}:"), proc.stderr[:300])
        # one more of each is the error
        with tempfile.TemporaryDirectory() as tmp:
            for text in (" +\n        ".join(["x"] * 8194), "x" + ".abs()" * 4097):
                path = os.path.join(tmp, "over.my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("fun main() {\n    let x = 1\n    print(" + text + ")\n}\n")
                proc = subprocess.run([myla, "check", path], capture_output=True, text=True, timeout=300)
                self.assertTrue(proc.stderr.startswith("parse error: more than 8192 operators"), proc.stderr[:300])

    def test_a_std_file_with_an_error_fails_the_comparison(self) -> None:
        # MYLA-416: `parse_main --lazy` tells a file that fails both ways
        # from one that reads, so that a broken library file isn't passed
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "broken.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("pub fun f() -> int {\n    return (1 +) * 2\n}\n")
            proc = subprocess.run([self._binary, "--lazy", path], capture_output=True, text=True)
            self.assertEqual(proc.stdout.strip(), "same error")

    def _continued(self, source: str) -> bool:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "garbled.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            return continues_a_line(path)

    def test_syntax_errors_match_the_oracle(self) -> None:
        for name, source in SYNTAX_ERRORS.items():
            with self.subTest(case=name):
                expected = SUPERSEDED.get(name) or _canonical(source)
                self.assertTrue(expected.startswith("err "), "not an error in Python")
                mine = self._myla_parse_source(source)
                if _receiverless(expected):
                    self.assertTrue(mine.startswith("err "), mine)
                    continue
                self.assertEqual(mine, expected)

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
                expected = _canonical(prefix)
                mine = self._myla_parse_source(prefix)
                if _receiverless(expected):
                    self.assertTrue(mine.startswith("err "), mine)
                    continue
                self.assertEqual(mine, expected)

    def test_garbled_sources_match_the_oracle(self) -> None:
        several = 0
        for path in recorded_examples():
            with open(recorded(path), encoding="utf-8") as fh:
                source = fh.read()
            for seed in range(4):
                garbled = _garbled(source, random.Random(f"{os.path.basename(path)}/{seed}"), 1 + 2 * seed)
                with self.subTest(file=os.path.basename(path), seed=seed):
                    expected = _canonical(garbled)
                    mine = self._myla_parse_source(garbled)
                    if self._continued(garbled) or _receiverless(expected):
                        # a line break the lexer leaves out since D104 (3): the
                        # recording parsed other tokens; errors still, no crash
                        self.assertEqual(mine.startswith("err "), expected.startswith("err "), mine)
                        continue
                    self.assertEqual(mine, expected)
                    several += expected.count("\nerr ") > 0
        # most garbled sources have several errors
        self.assertGreater(several, 50)

    def test_truncated_sources_match_the_oracle(self) -> None:
        for name in TRUNCATED:
            with open(recorded(os.path.join(_REPO, "examples", name)), encoding="utf-8") as fh:
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
                    expected = _canonical(prefix)
                    mine = self._myla_parse_source(prefix)
                    if _receiverless(expected):
                        self.assertTrue(mine.startswith("err "), mine)
                        continue
                    self.assertEqual(mine, expected)


if __name__ == "__main__":
    unittest.main()
