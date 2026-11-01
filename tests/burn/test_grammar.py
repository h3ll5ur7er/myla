"""Burn test: the grammar description `grammar/myla.ebnf` and what is generated
from it (MYLA-77).

- The wiki page Language/Grammar shows the same rules (compared in the
  canonical form `grammar canon` prints: annotations dropped, spacing and
  redundant groups normalised).
- `editor/tree-sitter-myla/grammar.js` and `queries/highlights.scm` are what
  `tools/grammar` generates: not edited by hand, not stale.
- The self-hosted parser accepts thousands of random programs sampled from
  the grammar, so the grammar allows nothing the compiler rejects.
- `keywords()` in `selfhost/tokens.my`, which the grammar must use in full, is
  the Python lexer's keyword table.
- The grammar tool's own `#test` cases pass.

With the tree-sitter CLI (`TREE_SITTER`, the package's `node_modules`, or
`PATH`) and a C compiler:

- `src/grammar.json` and `src/node-types.json` are what `tree-sitter generate`
  makes of the committed `grammar.js`;
- tree-sitter parses every `.my` file of `examples/`, `selfhost/`, `tools/` and
  the standard library, and the random programs, without an ERROR or MISSING
  node, so the grammar allows everything the compiler accepts;
- every lex and parse error of the error corpus gives an ERROR or MISSING node;
- the query files compile.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import myla_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_GRAMMAR = os.path.join(_REPO, "grammar", "myla.ebnf")
_WIKI = os.path.join(_REPO, "docs", "Language", "Grammar.md")
_TEMPLATE = os.path.join(_REPO, "tools", "grammar", "highlights.scm")
_PACKAGE = os.path.join(_REPO, "editor", "tree-sitter-myla")

SAMPLE_SEEDS = (1, 2)            # coverage builds up within a run, so few long runs
SAMPLES_PER_SEED = 5000
TREE_SITTER_SAMPLES = 2000


def _tree_sitter() -> str | None:
    """The tree-sitter CLI, if it and a C compiler are available."""
    if shutil.which("cc") is None:
        return None
    candidates = [os.environ.get("TREE_SITTER", ""),
                  os.path.join(_PACKAGE, "node_modules", ".bin", "tree-sitter"),
                  shutil.which("tree-sitter") or ""]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _corpus() -> list[str]:
    """Every Myla source file the compiler accepts."""
    files = (glob.glob(os.path.join(_REPO, "examples", "**", "*.my"), recursive=True)
             + glob.glob(os.path.join(_REPO, "selfhost", "*.my"))
             + glob.glob(os.path.join(_REPO, "tools", "**", "*.my"), recursive=True)
             + glob.glob(os.path.join(_REPO, "src", "myla", "std", "*.my")))
    errors = os.path.join(_REPO, "examples", "errors") + os.sep
    return sorted(f for f in files if not f.startswith(errors))


# Error-corpus files whose program the grammar accepts: they break a limit of
# the parsers, not a rule of the grammar (MYLA-182: 256 levels of nesting)
_PARSER_LIMITS = {"parse_nested_too_deeply.my"}


def _syntax_errors() -> list[str]:
    """The error-corpus files that must fail to lex or parse by the grammar."""
    out = []
    for path in sorted(glob.glob(os.path.join(_REPO, "examples", "errors", "*.my"))):
        if os.path.basename(path) in _PARSER_LIMITS:
            continue
        with open(path, encoding="utf-8") as fh:
            if re.match(r"//~\s*(lex|parse) error", fh.readline()):
                out.append(path)
    return out


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class GrammarDescription(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = myla_tool("tools/grammar/main.my", "grammar")

    def run_tool(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.tool, *argv], capture_output=True, text=True)

    def canon(self, path: str) -> list[str]:
        proc = self.run_tool("canon", path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.splitlines()

    @unittest.skipUnless(os.path.exists(_WIKI), "the wiki isn't in this checkout")
    def test_the_wiki_shows_the_grammar_file(self) -> None:
        wiki, ebnf = self.canon(_WIKI), self.canon(_GRAMMAR)
        self.assertEqual(sorted(set(wiki) - set(ebnf)), [], "rules on the wiki page only (or different)")
        self.assertEqual(sorted(set(ebnf) - set(wiki)), [], "rules in grammar/myla.ebnf only (or different)")

    def test_generated_files_are_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "queries"))
            proc = self.run_tool("treesitter", _GRAMMAR, _TEMPLATE, tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for name in ("grammar.js", os.path.join("queries", "highlights.scm")):
                with self.subTest(file=name):
                    with open(os.path.join(tmp, name), encoding="utf-8") as fh:
                        fresh = fh.read()
                    with open(os.path.join(_PACKAGE, name), encoding="utf-8") as fh:
                        committed = fh.read()
                    self.assertEqual(committed, fresh, f"{name} is stale: run scripts/gen_treesitter.sh")

    def test_the_self_hosted_parser_accepts_samples(self) -> None:
        for seed in SAMPLE_SEEDS:
            with self.subTest(seed=seed):
                proc = self.run_tool("sample", _GRAMMAR, str(seed), str(SAMPLES_PER_SEED), "parse")
                self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr)

    def test_the_keyword_list_is_the_lexer_s(self) -> None:
        # The grammar check asks for every word of keywords() in
        # selfhost/tokens.my, so that list must be complete: the Python
        # lexer's table is the reference.
        from myla.tokens import KEYWORDS
        with open(os.path.join(_REPO, "selfhost", "tokens.my"), encoding="utf-8") as fh:
            body = re.search(r"pub fun keywords\(\) -> \[str\] \{\s*return \[(.*?)\]", fh.read(), re.S)
        self.assertIsNotNone(body, "keywords() not found in selfhost/tokens.my")
        self.assertEqual(sorted(re.findall(r'"(\w+)"', body.group(1))), sorted(KEYWORDS))

    def test_the_tool_s_own_tests_pass(self) -> None:
        sources = sorted(glob.glob(os.path.join(_REPO, "tools", "grammar", "*.my")))
        sources.append(os.path.join(_REPO, "selfhost", "tokens.my"))
        for path in sources:
            with self.subTest(file=os.path.relpath(path, _REPO)):
                proc = subprocess.run([sys.executable, os.path.join(_REPO, "myla.py"), "test", path],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


@unittest.skipUnless(CAN_BUILD_NATIVE and _tree_sitter() is not None,
                     "needs the tree-sitter CLI (npm install in editor/tree-sitter-myla) and cc")
class TreeSitterGrammar(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ts = _tree_sitter()
        cls.tool = myla_tool("tools/grammar/main.my", "grammar")
        # The CLI caches the compiled parser by language name and reuses it
        # while it is newer than src/parser.c, so another checkout's `myla`
        # grammar could stand in for this one: build it afresh once.
        proc = subprocess.run([cls.ts, "parse", "-q", "--rebuild", os.path.join(_REPO, "examples", "hello.my")],
                              cwd=_PACKAGE, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"tree-sitter could not build the parser:\n{proc.stdout}{proc.stderr}")

    def parse(self, paths: list[str]) -> subprocess.CompletedProcess:
        """`tree-sitter parse -q` over `paths`: it prints a line for each file
        with an ERROR or MISSING node and then exits with 1."""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("\n".join(paths) + "\n")
            listing = fh.name
        try:
            return subprocess.run([self.ts, "parse", "-q", "--paths", listing], cwd=_PACKAGE,
                                  capture_output=True, text=True)
        finally:
            os.remove(listing)

    def test_src_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("grammar.js", "tree-sitter.json"):
                shutil.copy(os.path.join(_PACKAGE, name), tmp)
            proc = subprocess.run([self.ts, "generate", "--abi", "14"], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for name in ("grammar.json", "node-types.json"):
                with self.subTest(file=name):
                    with open(os.path.join(tmp, "src", name), encoding="utf-8") as fh:
                        fresh = fh.read()
                    with open(os.path.join(_PACKAGE, "src", name), encoding="utf-8") as fh:
                        committed = fh.read()
                    self.assertEqual(committed, fresh, f"src/{name} is stale: run scripts/gen_treesitter.sh")

    def test_parses_every_source_file(self) -> None:
        proc = self.parse(_corpus())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_parses_samples(self) -> None:
        proc = subprocess.run([self.tool, "sample", _GRAMMAR, "7", str(TREE_SITTER_SAMPLES)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        parts = re.split(r"^// sample (\d+)\n", proc.stdout, flags=re.M)
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i in range(1, len(parts), 2):
                path = os.path.join(tmp, f"sample_{int(parts[i]):04d}.my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(parts[i + 1])
                paths.append(path)
            self.assertEqual(len(paths), TREE_SITTER_SAMPLES)
            result = self.parse(paths)
            self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr)

    def test_syntax_errors_give_error_nodes(self) -> None:
        files = _syntax_errors()
        self.assertGreater(len(files), 15)
        proc = self.parse(files)
        flagged = {line.split("\t")[0].strip() for line in proc.stdout.splitlines() if line.strip()}
        for path in files:
            with self.subTest(file=os.path.basename(path)):
                self.assertIn(path, flagged, "parsed without an ERROR or MISSING node")

    def test_queries_compile(self) -> None:
        sample = os.path.join(_REPO, "examples", "control_flow.my")
        for query in sorted(glob.glob(os.path.join(_PACKAGE, "queries", "*.scm"))):
            with self.subTest(query=os.path.basename(query)):
                proc = subprocess.run([self.ts, "query", query, sample], cwd=_PACKAGE,
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
