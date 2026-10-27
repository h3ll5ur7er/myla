"""The VS Code extension's static files describe the real language (MYLA-54):
the TextMate grammar's keywords and type names come from the compiler's, and
every snippet, expanded with its default text, parses. Also runs the
extension's own unit tests (`test/unit/*.test.ts`, MYLA-99, MYLA-100) under
node, which needs no `npm ci`."""
import json
import os
import re
import shutil
import subprocess
import unittest

from myla.lexer import tokenize
from myla.parser import parse
from myla.tokens import KEYWORDS

_EXT = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "vscode-extension", "myla")

# The built-in type names (the checker resolves these identifiers).
TYPE_NAMES = {"int", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64",
              "float", "float32", "float64", "bool", "str", "char"}
# Words of the removed Rust dialect, and type names Myla doesn't have (`f32`
# and `f64` are literal suffixes, never types: see `test_type_names`).
NOT_MYLA = {"actor", "async", "await", "spawn", "go", "chan", "select", "void", "unit"}
# Snippets that are declarations; the others are statements or expressions.
DECLARATIONS = {"fun", "funv", "struct", "enum", "trait", "impl", "implfor", "typealias", "const",
                "import", "from", "test"}


def _load(name: str):
    with open(os.path.join(_EXT, name), encoding="utf-8") as fh:
        return json.load(fh)


def _words(pattern: str) -> set[str]:
    """The literal words of a `\\b(a|b|c)\\b` pattern."""
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", pattern.replace("\\b", " ")))


def _expand(body) -> str:
    """A snippet with every placeholder replaced by its default text."""
    text = "\n".join(body) if isinstance(body, list) else body
    while re.search(r"\$\{\d+:[^${}]*\}", text):
        text = re.sub(r"\$\{\d+:([^${}]*)\}", r"\1", text)
    return re.sub(r"\$\{?\d+\}?", "", text)


class TestTextMateGrammar(unittest.TestCase):
    def setUp(self):
        self.repo = _load("syntaxes/myla.tmLanguage.json")["repository"]

    def test_keywords_are_myla_keywords(self):
        words = set()
        for p in self.repo["keywords"]["patterns"]:
            words |= _words(p["match"])
        self.assertLessEqual(words, set(KEYWORDS) - {"true", "false", "self"})
        self.assertLessEqual({"if", "else", "match", "while", "for", "in", "break", "continue",
                              "return", "let", "var", "pub", "import", "from", "as"}, words)

    def test_type_names(self):
        [prim] = [p for p in self.repo["types"]["patterns"] if p["name"].startswith("support.type")]
        self.assertEqual(_words(prim["match"]), TYPE_NAMES)

    def test_no_words_of_other_languages(self):
        text = json.dumps(self.repo)
        for word in NOT_MYLA:
            with self.subTest(word=word):
                self.assertNotRegex(text, rf"\b{word}\b")

    def test_literals(self):
        number = [p["match"] for p in self.repo["numbers"]["patterns"]]
        for lit in ("1.5", "1e9", "2f32", "1.5e-3f64", "0xFFu8", "0b1010i64", "0o17", "42", "255u8"):
            with self.subTest(lit=lit):
                self.assertTrue(any(re.fullmatch(p.replace("\\b", ""), lit) for p in number))
        char = self.repo["chars"]["patterns"][0]["match"]
        for lit in ("'a'", "'\\n'", "'\\u{1F600}'"):
            with self.subTest(lit=lit):
                self.assertRegex(lit, char)


class TestSnippets(unittest.TestCase):
    def test_every_snippet_parses(self):
        for name, snippet in _load("snippets/myla.code-snippets").items():
            with self.subTest(snippet=name):
                code = _expand(snippet["body"])
                if snippet["prefix"] not in DECLARATIONS:
                    code = "fun main() {\n" + code + "\n}\n"
                parse(tokenize(code + "\n"))

    def test_no_snippets_for_other_languages(self):
        for name, snippet in _load("snippets/myla.code-snippets").items():
            with self.subTest(snippet=name):
                self.assertFalse(_words(_expand(snippet["body"])) & NOT_MYLA)


def _node_strips_types() -> bool:
    if shutil.which("node") is None:
        return False
    return subprocess.run(["node", "--experimental-strip-types", "-e", "0"], capture_output=True).returncode == 0


@unittest.skipUnless(_node_strips_types(), "needs node 22.6+")
class TestExtensionUnitTests(unittest.TestCase):
    """The extension's TypeScript unit tests: the GDB/MI parser, the DAP
    framing, the debug adapter against a fake gdb, how values and stops are
    presented, finding the CLI and building for the debugger. The test of the
    bundle is left to `npm test`, which builds it first."""

    def test_the_extension_s_unit_tests_pass(self):
        tests = sorted(os.path.join("test", "unit", f) for f in os.listdir(os.path.join(_EXT, "test", "unit"))
                       if f.endswith(".test.ts"))
        proc = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "--test",
                               "--test-skip-pattern=bundle", *tests],
                              cwd=_EXT, capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stdout[-4000:] + proc.stderr[-2000:])
        self.assertRegex(proc.stdout, r"# pass [1-9]")
        self.assertIn("# fail 0", proc.stdout)


if __name__ == "__main__":
    unittest.main()
