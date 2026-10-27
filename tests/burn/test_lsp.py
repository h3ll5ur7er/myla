"""Burn tests: the language server written in Myla (`tools/lsp`, MYLA-80).

It runs the scenarios the Python server runs (tests/integration/
test_lsp_diagnostics.py), plus what only it promises: a malformed message gets
a parse error, a burst of changes is checked once (the debounce), and its
memory stays flat over hundreds of checks. Both builds run them: by the
Python backend and by the self-hosted one (as scripts/bootstrap.sh builds
build/myla-lsp), which leaked where the other didn't.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest

from myla.loader import default_stdlib_root

from ._native import CAN_BUILD_NATIVE, SKIP_REASON

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
from ._tools import myla_tool, selfhost_tool
from tests.integration.test_lsp_diagnostics import HAVE_PYGLS, LspScenarios, _Client, _uri
from tests.integration.test_lsp_requests import LspRequestScenarios


_TMP = tempfile.TemporaryDirectory()


def _self_hosted_build() -> str:
    """The server compiled by the self-hosted compiler (once per run)."""
    binary = os.path.join(_TMP.name, "myla-lsp")
    if not os.path.exists(binary):
        asm = subprocess.run([selfhost_tool("gen_main"), os.path.join(_REPO, "tools", "lsp", "main.my"),
                              default_stdlib_root()], capture_output=True, text=True, check=True)
        with open(binary + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm.stdout)
        subprocess.run(["as", "--64", "-o", binary + ".o", binary + ".s"], check=True)
        subprocess.run(["ld", "-o", binary, binary + ".o"], check=True)
    return binary


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestMylaLsp(LspScenarios, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = myla_tool("tools/lsp/main.my", "lsp")

    def server_command(self) -> list[str]:
        return [self.binary, "--stdlib", default_stdlib_root()]

    def test_a_malformed_message_is_a_parse_error(self):
        self.client.send_raw(b"{not json")
        msg = self.client.receive()
        self.assertEqual(msg["error"]["code"], -32700)
        self.assertIsNone(msg["id"])
        # and the server keeps going
        rid = self.client.send("shutdown", None, request=True)
        self.assertIsNone(self.client.response(rid)["result"])

    def test_a_burst_of_changes_is_checked_once(self):
        self.open(self.bad, "pub fun f() -> int {\n    return 1\n}\n")
        self.client.diagnostics(1)
        body = b""
        for v in range(2, 40):
            body_text = "pub fun f() -> int {\n    return %s\n}\n" % ("1" if v < 39 else "true")
            msg = json.dumps({"jsonrpc": "2.0", "method": "textDocument/didChange", "params": {
                "textDocument": {"uri": _uri(self.bad), "version": v},
                "contentChanges": [{"text": body_text}]}}).encode()
            body += b"Content-Length: %d\r\n\r\n" % len(msg) + msg
        self.client.proc.stdin.write(body)            # all at once
        self.client.proc.stdin.flush()
        got = self.client.diagnostics(1)[_uri(self.bad)]
        self.assertEqual(len(got), 1)                 # the last text, checked once
        rid = self.client.send("shutdown", None, request=True)
        self.client.response(rid)                     # no other diagnostics came first
        self.assertTrue(self.client.messages.empty())

    def test_memory_stays_flat(self):
        # std/json.my matches on Option and Result throughout: checking it
        # leaked about 7 kB a time before loops released what they iterate on
        # an early return, and the Python backend reused large cells (MYLA-80)
        path = os.path.join(_REPO, "src", "myla", "std", "json.my")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        uri = _uri(path)
        self.client.send("textDocument/didOpen", {"textDocument": {
            "uri": uri, "languageId": "myla", "version": 1, "text": text}})
        self.assertEqual(self.client.diagnostics(1), {uri: []})

        def rss_kb() -> int:
            with open(f"/proc/{self.client.proc.pid}/status") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1])
            return 0

        def churn(n: int, start: int) -> None:
            for v in range(start, start + n):
                self.client.send("textDocument/didChange", {
                    "textDocument": {"uri": uri, "version": v},
                    "contentChanges": [{"text": text + "\n" * (v % 5)}]})
                # a save checks at once (a change alone waits out the debounce)
                self.client.send("textDocument/didSave", {"textDocument": {"uri": uri}})
                self.client.diagnostics(1)

        churn(20, 2)
        before = rss_kb()
        churn(200, 100)
        after = rss_kb()
        self.assertLess(after - before, 256, f"RSS grew from {before} kB to {after} kB")

@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestMylaLspSelfHosted(TestMylaLsp):
    """The same server compiled by the self-hosted compiler."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = _self_hosted_build()


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestMylaLspRequests(LspRequestScenarios, unittest.TestCase):
    """Symbols, definition, references, hover and completion (step 2)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = myla_tool("tools/lsp/main.my", "lsp")

    def server_command(self) -> list[str]:
        return [self.binary, "--stdlib", default_stdlib_root()]


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestMylaLspRequestsSelfHosted(TestMylaLspRequests):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = _self_hosted_build()


LEGEND_TYPES = ["namespace", "type", "enum", "interface", "struct", "typeParameter", "parameter", "variable",
                "property", "enumMember", "function", "method", "keyword", "comment", "string", "number",
                "operator", "decorator"]

SEMANTIC_SOURCE = (
    "from std.io import println   // a comment\n"
    "/* a block\n"
    "   comment */\n"
    "struct Point { x: int, y: int }\n"
    "enum Shape { Dot, Box(int) }\n"
    "const MAX: int = 255u8 as int\n"
    "#test(1)[2]\n"
    "fun twice(n: int) -> int {\n"
    "    let p = Point { x: n, y: 2 }\n"
    "    let s = Shape.Box(p.x)\n"
    "    println(f\"😀 {p.y} of {MAX}\")\n"
    "    return p.len() + 'a' as int\n"
    "}\n"
)


def decode_tokens(data: list, lines: list) -> list:
    """(line, start, length, type, modifiers, text) for LSP semantic tokens
    (UTF-16 offsets; `text` sliced from the line by code points, the lines
    here being in the BMP except where a test says otherwise)."""
    out = []
    line = start = 0
    for i in range(0, len(data), 5):
        dl, ds, length, typ, mods = data[i:i + 5]
        line += dl
        start = start + ds if dl == 0 else ds
        units = lines[line].encode("utf-16-le")
        text = units[2 * start:2 * (start + length)].decode("utf-16-le")
        mod_names = [m for b, m in enumerate(["declaration", "readonly"]) if mods & (1 << b)]
        out.append((line, start, length, LEGEND_TYPES[typ], mod_names, text))
    return out


class SemanticTokenScenarios:
    """Semantic tokens (step 3): a subclass names the server binary."""

    def semantic(self, text: str, name: str = "sem.my") -> list:
        root = tempfile.mkdtemp(prefix="myla_sem_")
        self.addCleanup(__import__("shutil").rmtree, root, True)
        path = os.path.join(root, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        c = _Client([self.binary, "--stdlib", default_stdlib_root()])
        self.addCleanup(c.close)
        rid = c.send("initialize", {"processId": None, "rootUri": _uri(root), "capabilities": {}}, request=True)
        caps = c.response(rid)["result"]["capabilities"]
        self.assertEqual(caps["semanticTokensProvider"]["legend"]["tokenTypes"], LEGEND_TYPES)
        self.assertEqual(caps["semanticTokensProvider"]["legend"]["tokenModifiers"], ["declaration", "readonly"])
        c.send("textDocument/didOpen", {"textDocument": {"uri": _uri(path), "languageId": "myla", "version": 1,
                                                          "text": text}})
        rid = c.send("textDocument/semanticTokens/full", {"textDocument": {"uri": _uri(path)}}, request=True)
        return decode_tokens(c.response(rid)["result"]["data"], text.splitlines())

    def kinds(self, tokens: list) -> list:
        return [(t[5], t[3], t[4]) for t in tokens]

    def test_classification(self) -> None:
        got = self.kinds(self.semantic(SEMANTIC_SOURCE))
        expect = [
            ("from", "keyword", []), ("std", "namespace", []), ("io", "namespace", []),
            ("import", "keyword", []), ("println", "function", []), ("// a comment", "comment", []),
            ("/* a block", "comment", []), ("   comment */", "comment", []),
            ("struct", "keyword", []), ("Point", "struct", ["declaration"]), ("x", "property", ["declaration"]),
            ("int", "type", []), ("y", "property", ["declaration"]), ("int", "type", []),
            ("enum", "keyword", []), ("Shape", "enum", ["declaration"]), ("Dot", "enumMember", ["declaration"]),
            ("Box", "enumMember", ["declaration"]), ("int", "type", []),
            ("const", "keyword", []), ("MAX", "variable", ["declaration", "readonly"]), ("int", "type", []),
            ("=", "operator", []), ("255u8", "number", []), ("as", "keyword", []), ("int", "type", []),
            ("test", "decorator", []), ("1", "number", []), ("2", "number", []),
            ("fun", "keyword", []), ("twice", "function", ["declaration"]), ("n", "variable", []),
            ("int", "type", []), ("->", "operator", []), ("int", "type", []),
            ("let", "keyword", []), ("p", "variable", []), ("=", "operator", []), ("Point", "struct", []),
            ("x", "property", []), ("n", "variable", []), ("y", "property", []), ("2", "number", []),
            ("let", "keyword", []), ("s", "variable", []), ("=", "operator", []), ("Shape", "enum", []),
            ("Box", "enumMember", []), ("p", "variable", []), ("x", "property", []),
            ("println", "function", []), ('f"😀 ', "string", []), ("p", "variable", []), ("y", "property", []),
            (" of ", "string", []), ("MAX", "variable", ["readonly"]), ('"', "string", []),
            ("return", "keyword", []), ("p", "variable", []), ("len", "method", []), ("+", "operator", []),
            ("'a'", "string", []), ("as", "keyword", []), ("int", "type", []),
        ]
        self.assertEqual(got, expect)

    def test_utf16_offsets(self) -> None:
        tokens = self.semantic('fun f() {\n    let s = "😀😀"; let t = s\n}\n')
        t = [x for x in tokens if x[5] == "t"][0]
        self.assertEqual((t[0], t[1], t[2]), (1, 24, 1))   # code point 22, after two astral characters: +2

    def test_a_lex_error_gives_no_tokens(self) -> None:
        self.assertEqual(self.semantic('fun f() {\n    let s = "open\n}\n'), [])

    def test_the_corpus_is_covered(self) -> None:
        import glob, re
        keywords = set(open(os.path.join(_REPO, "selfhost", "tokens.my")).read().split("keywords() -> [str] {")[1]
                       .split("]")[0].replace('"', "").replace("return [", "").replace(",", " ").split())
        files = sorted(glob.glob(os.path.join(_REPO, "examples", "*.my")) + glob.glob(os.path.join(_REPO, "selfhost", "*.my")))
        for path in files:
            with self.subTest(file=os.path.relpath(path, _REPO)):
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                lines = text.splitlines()
                tokens = self.semantic(text, os.path.basename(path))
                self.assertTrue(tokens)
                covered = [bytearray(len(l.encode("utf-16-le")) // 2) for l in lines]
                last = (-1, -1)
                for line, start, length, typ, mods, tok in tokens:
                    self.assertGreater((line, start), last, "tokens out of order")
                    self.assertGreater(length, 0)
                    self.assertLessEqual(start + length, len(covered[line]), "past the end of the line")
                    self.assertFalse(any(covered[line][start:start + length]), f"overlap at {line}:{start}")
                    covered[line][start:start + length] = b"\x01" * length
                    last = (line, start + length - 1)
                    if typ == "keyword":
                        self.assertIn(tok, keywords | {"_"})
                    elif typ == "number":
                        self.assertRegex(tok, r"^[0-9]")
                    elif typ == "comment":
                        self.assertNotEqual(tok.strip(), "")
                    elif typ in ("variable", "function", "method", "property", "type", "struct", "enum",
                                 "enumMember", "interface", "namespace", "decorator"):
                        self.assertRegex(tok, r"^[A-Za-z_][A-Za-z0-9_]*$")
                # every character that isn't white space or punctuation has a token
                for n, line in enumerate(lines):
                    units = line.encode("utf-16-le")
                    for k in range(len(covered[n])):
                        ch = units[2 * k:2 * k + 2].decode("utf-16-le", "replace")
                        if not covered[n][k] and not ch.isspace() and ch not in "()[]{},.:;#\ufffd":
                            self.fail(f"line {n + 1} column {k + 1}: {ch!r} has no token: {line!r}")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestSemanticTokens(SemanticTokenScenarios, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = myla_tool("tools/lsp/main.my", "lsp")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestSemanticTokensSelfHosted(TestSemanticTokens):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = _self_hosted_build()


class TestOwnTests(unittest.TestCase):
    def test_the_server_s_own_tests_pass(self) -> None:
        # server.my imports every other module of tools/lsp (and std.json, std.num)
        import sys
        proc = subprocess.run([sys.executable, os.path.join(_REPO, "myla.py"), "test",
                               os.path.join(_REPO, "tools", "lsp", "server.my")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


def _strip_range_ends(symbols: list) -> list:
    """Document symbols without the end of `range`, where the servers differ
    on purpose: the Python one ends it at the last line an AST node is on,
    the Myla one at the declaration's last token."""
    out = []
    for s in symbols:
        s = dict(s)
        s["range"] = {"start": s["range"]["start"]}
        s["children"] = _strip_range_ends(s.get("children", []))
        out.append(s)
    return out


@unittest.skipUnless(CAN_BUILD_NATIVE and HAVE_PYGLS, "needs a native toolchain and the lsp extra (pygls)")
class TestAgainstThePythonServer(unittest.TestCase):
    """The Myla server answers what the Python server answers, on real files:
    document symbols for every example and compiler source, and definition,
    hover, references and completion at sampled positions in the examples
    (with examples/ as the workspace)."""

    @classmethod
    def setUpClass(cls) -> None:
        import sys
        cls.root = os.path.join(_REPO, "examples")
        cls.servers = []
        for argv in ([sys.executable, os.path.join(_REPO, "myla.py"), "lsp"],
                     [myla_tool("tools/lsp/main.my", "lsp"), "--stdlib", default_stdlib_root()]):
            c = _Client(argv)
            c.TIMEOUT = 60
            rid = c.send("initialize", {"processId": None, "rootUri": _uri(cls.root), "capabilities": {}},
                         request=True)
            c.response(rid)
            c.send("initialized", {})
            cls.servers.append(c)

    @classmethod
    def tearDownClass(cls) -> None:
        for c in cls.servers:
            c.close()

    def ask(self, method: str, params: dict) -> list:
        answers = []
        for c in self.servers:
            rid = c.send(method, params, request=True)
            answers.append(c.response(rid).get("result"))
        return answers

    def open(self, path: str) -> tuple[str, str]:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for c in self.servers:
            c.send("textDocument/didOpen", {"textDocument": {
                "uri": _uri(path), "languageId": "myla", "version": 1, "text": text}})
        return _uri(path), text

    def close_doc(self, uri: str) -> None:
        for c in self.servers:
            c.send("textDocument/didClose", {"textDocument": {"uri": uri}})

    def test_document_symbols(self) -> None:
        import glob
        files = sorted(glob.glob(os.path.join(self.root, "*.my")) + glob.glob(os.path.join(_REPO, "selfhost", "*.my"))
                       + glob.glob(os.path.join(_REPO, "tools", "*", "*.my"))
                       + glob.glob(os.path.join(_REPO, "src", "myla", "std", "*.my")))
        self.assertGreater(len(files), 50)
        for path in files:
            with self.subTest(file=os.path.relpath(path, _REPO)):
                uri, _ = self.open(path)
                py, my = self.ask("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
                self.assertTrue(py, "no symbols")
                self.assertEqual(_strip_range_ends(my), _strip_range_ends(py))
                self.close_doc(uri)

    def declares(self, location: dict, name: str) -> bool:
        """Whether `location` is the name of a declaration of `name`."""
        from tests.integration.test_lsp_diagnostics import _uri as to_uri
        path = location["uri"][len("file://"):]
        with open(path, encoding="utf-8") as fh:
            line = fh.read().splitlines()[location["range"]["start"]["line"]]
        r = location["range"]
        # the range counts UTF-16 units; the examples are ASCII where names are
        return line[r["start"]["character"]:r["end"]["character"]] == name

    def test_requests_at_identifiers(self) -> None:
        import glob, re
        files = sorted(glob.glob(os.path.join(self.root, "*.my")))
        checked = 0
        for path in files:
            uri, text = self.open(path)
            lines = text.splitlines()
            idents = [(i, m.start(), m.group()) for i, line in enumerate(lines)
                      for m in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", line) if line.isascii()]
            for n, (line, col, name) in enumerate(idents[::max(1, len(idents) // 12)]):
                with self.subTest(file=os.path.basename(path), line=line, name=name):
                    pos = {"textDocument": {"uri": uri}, "position": {"line": line, "character": col}}
                    py, my = self.ask("textDocument/definition", pos)
                    if py != my:
                        # a name declared in several files: either declaration will do
                        self.assertIsNotNone(py)
                        self.assertIsNotNone(my)
                        self.assertTrue(self.declares(my, name), my)
                    hp, hm = self.ask("textDocument/hover", pos)
                    if py == my:
                        self.assertEqual(hm, hp)
                    if n % 4 == 0:
                        rp, rm = self.ask("textDocument/references", dict(pos, context={"includeDeclaration": n % 8 == 0}))
                        key = lambda locs: sorted((l["uri"], str(l["range"])) for l in (locs or []))
                        self.assertEqual(key(rm), key(rp))
                    checked += 1
            for line in (0, len(lines) // 2):
                with self.subTest(file=os.path.basename(path), completion=line):
                    cp, cm = self.ask("textDocument/completion", {"textDocument": {"uri": uri},
                                                                  "position": {"line": line, "character": 0}})
                    labels = lambda c: sorted({(i["label"], i["kind"]) for i in c["items"]})
                    self.assertEqual(labels(cm), labels(cp))
            for line, text_line in enumerate(lines):
                dot = text_line.find(".")
                if dot > 0 and text_line.isascii():
                    with self.subTest(file=os.path.basename(path), member_completion=line):
                        cp, cm = self.ask("textDocument/completion", {"textDocument": {"uri": uri},
                                                                      "position": {"line": line, "character": dot + 1}})
                        labels = lambda c: sorted({(i["label"], i["kind"]) for i in c["items"]})
                        self.assertEqual(labels(cm), labels(cp))
                    break
            self.close_doc(uri)
        self.assertGreater(checked, 200)


if __name__ == "__main__":
    unittest.main()
