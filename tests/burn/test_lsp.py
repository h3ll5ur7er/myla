"""Burn tests: the language server written in Myla (`tools/lsp`, MYLA-80).

It runs the shared scenarios (tests/burn/_lsp_scenarios.py, once also run
against the retired Python server, MYLA-83), plus what only it promises: a
malformed message gets a parse error, a burst of changes is checked once (the
debounce), and its memory stays flat over hundreds of checks. Both builds run them: by the
Python backend and by the self-hosted one (as scripts/bootstrap.sh builds
build/myla-lsp), which leaked where the other didn't.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

from myla.loader import default_stdlib_root

from ._native import CAN_BUILD_NATIVE, SKIP_REASON

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
from ._tools import myla_tool, selfhost_tool
from ._lsp_scenarios import LspScenarios, LspRequestHelpers, LspRequestScenarios, _Client, _uri, rng


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


class RobustnessScenarios(LspRequestHelpers):
    """What the Myla server does beyond the Python one (MYLA-51, step 4)."""

    GOOD = "struct P { x: int }\nfun get(p: P) -> int {\n    return p.x\n}\nfun main() {\n    print(get(P { x: 1 }))\n}\n"

    def change(self, uri, text, version=2):
        self.client.send("textDocument/didChange", {"textDocument": {"uri": uri, "version": version},
                                                     "contentChanges": [{"text": text}]})

    def test_a_lex_error_keeps_the_last_good_parse(self):
        uri = self.open(self.GOOD)
        self.assertEqual([s["name"] for s in self.request("textDocument/documentSymbol", uri)], ["P", "get", "main"])
        # a half-typed string on a new last line: the file no longer lexes
        self.change(uri, self.GOOD + "fun later() {\n    let s = \"unfinished\n")
        self.assertEqual([s["name"] for s in self.request("textDocument/documentSymbol", uri)], ["P", "get", "main"])
        self.assertEqual(self.at("textDocument/definition", uri, 5, 11), {"uri": uri, "range": rng(1, 4, 7)})
        hover = self.at("textDocument/hover", uri, 5, 11)
        self.assertEqual(hover["contents"]["value"], "```myla\nfun get(p: P) -> int\n```")

    def test_a_parse_error_keeps_the_last_good_outline(self):
        uri = self.open(self.GOOD)
        self.change(uri, self.GOOD.replace("fun main() {", "fun main( {"))
        self.assertEqual([s["name"] for s in self.request("textDocument/documentSymbol", uri)], ["P", "get", "main"])
        labels = {i["label"] for i in self.at("textDocument/completion", uri, 5, 4)["items"]}
        self.assertIn("get", labels)

    def test_completion_triggers_on_a_dot(self):
        self.assertEqual(self.capabilities["completionProvider"].get("triggerCharacters"), ["."])

    def test_added_workspace_folders_are_searched(self):
        self.assertTrue(self.capabilities["workspace"]["workspaceFolders"]["changeNotifications"])
        other = tempfile.mkdtemp(prefix="myla_lsp_other_")
        self.addCleanup(__import__("shutil").rmtree, other, True)
        with open(os.path.join(other, "lib.my"), "w", encoding="utf-8") as fh:
            fh.write("pub fun helper() -> int {\n    return 1\n}\n")
        uri = self.open("fun main() {\n    print(helper())\n}\n")
        self.assertIsNone(self.at("textDocument/definition", uri, 1, 11))
        self.client.send("workspace/didChangeWorkspaceFolders", {"event": {
            "added": [{"uri": _uri(other), "name": "other"}], "removed": []}})
        self.assertEqual(self.at("textDocument/definition", uri, 1, 11),
                         {"uri": _uri(os.path.join(other, "lib.my")), "range": rng(0, 8, 14)})
        self.client.send("workspace/didChangeWorkspaceFolders", {"event": {
            "added": [], "removed": [{"uri": _uri(other), "name": "other"}]}})
        self.assertIsNone(self.at("textDocument/definition", uri, 1, 11))

    def test_watched_file_changes_are_seen(self):
        lib = self.write("lib.my", "pub fun helper() -> int {\n    return 1\n}\n")
        uri = self.open("fun main() {\n    print(helper())\n}\n")
        self.assertEqual(self.at("textDocument/definition", uri, 1, 11)["range"], rng(0, 8, 14))
        with open(lib, "w", encoding="utf-8") as fh:
            fh.write("\n\npub fun helper() -> int {\n    return 2\n}\n")
        self.client.send("workspace/didChangeWatchedFiles", {"changes": [{"uri": _uri(lib), "type": 2}]})
        self.assertEqual(self.at("textDocument/definition", uri, 1, 11)["range"], rng(2, 8, 14))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestMylaLspRobustness(RobustnessScenarios, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = myla_tool("tools/lsp/main.my", "lsp")

    def server_command(self) -> list[str]:
        return [self.binary, "--stdlib", default_stdlib_root()]


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestMylaLspRobustnessSelfHosted(TestMylaLspRobustness):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = _self_hosted_build()


SCOPES = ("fun total(xs: [int]) -> int {\n"     # 0
          "    var total = 0\n"                      # 1
          "    for x in xs {\n"                      # 2
          "        total = total + x\n"              # 3
          "    }\n"                                  # 4
          "    return total\n"                       # 5
          "}\n"                                      # 6
          "fun main() {\n"                           # 7
          "    let xs = [1, 2]\n"                    # 8
          "    print(total(xs))\n"                   # 9
          "}\n")

KINDS = ("enum Color { Red, Green }\n"                                  # 0
         "enum Light { Red, Off }\n"                                     # 1
         "struct P { x: int }\n"                                         # 2
         "struct Q { x: int }\n"                                         # 3
         "fun first<T>(xs: [T], f: (T) -> T) -> T {\n"                   # 4
         "    return f(xs[0])\n"                                         # 5
         "}\n"                                                           # 6
         "fun main() {\n"                                                # 7
         "    let c = Color.Red\n"                                       # 8
         "    let p = P { x: 1 }\n"                                      # 9
         "    match c {\n"                                               # 10
         "        Color.Red => print(first([p.x], (v: int) => v + 1)),\n"  # 11
         "        _ => {},\n"                                            # 12
         "    }\n"                                                       # 13
         "    match Some(p) {\n"                                         # 14
         "        Some(P { x: n }) => print(n),\n"                       # 15
         "        None => {},\n"                                         # 16
         "    }\n"                                                       # 17
         "}\n")


class ScopeScenarios(LspRequestHelpers):
    """Definition, hover and references resolved by scope and imports
    (MYLA-51, step 5): a name means the declaration in scope where it is
    used, not any declaration so named."""

    def defn(self, uri, line, character):
        return self.at("textDocument/definition", uri, line, character)

    def hover(self, uri, line, character):
        h = self.at("textDocument/hover", uri, line, character)
        return h and h["contents"]["value"].removeprefix("```myla\n").removesuffix("\n```")

    def refs(self, uri, line, character, decl=True):
        found = self.at("textDocument/references", uri, line, character, context={"includeDeclaration": decl})
        return sorted((l["uri"], l["range"]["start"]["line"], l["range"]["start"]["character"],
                       l["range"]["end"]["character"]) for l in found)

    def test_locals_and_parameters(self):
        uri = self.open(SCOPES)
        self.assertEqual(self.defn(uri, 3, 8), {"uri": uri, "range": rng(1, 8, 13)})      # the local
        self.assertEqual(self.defn(uri, 3, 16), {"uri": uri, "range": rng(1, 8, 13)})
        self.assertEqual(self.defn(uri, 9, 10), {"uri": uri, "range": rng(0, 4, 9)})      # the function
        self.assertEqual(self.defn(uri, 2, 13), {"uri": uri, "range": rng(0, 10, 12)})    # the parameter
        self.assertEqual(self.defn(uri, 9, 16), {"uri": uri, "range": rng(8, 8, 10)})     # main's xs
        self.assertEqual(self.defn(uri, 3, 24), {"uri": uri, "range": rng(2, 8, 9)})      # the loop variable
        self.assertEqual(self.hover(uri, 3, 8), "var total: int")
        self.assertEqual(self.hover(uri, 3, 24), "let x: int")
        self.assertEqual(self.hover(uri, 2, 13), "xs: [int]")
        self.assertEqual(self.hover(uri, 9, 10), "fun total(xs: [int]) -> int")

    def test_references_follow_the_declaration(self):
        uri = self.open(SCOPES)
        self.assertEqual(self.refs(uri, 3, 8), [(uri, 1, 8, 13), (uri, 3, 8, 13), (uri, 3, 16, 21), (uri, 5, 11, 16)])
        self.assertEqual(self.refs(uri, 3, 8, decl=False), [(uri, 3, 8, 13), (uri, 3, 16, 21), (uri, 5, 11, 16)])
        self.assertEqual(self.refs(uri, 0, 4), [(uri, 0, 4, 9), (uri, 9, 10, 15)])
        self.assertEqual(self.refs(uri, 8, 8), [(uri, 8, 8, 10), (uri, 9, 16, 18)])

    def test_references_in_other_files_skip_their_locals(self):
        other = self.write("other.my", "fun use_it() -> int {\n    let total = 1\n    return total\n}\n")
        uri = self.open(SCOPES)
        self.assertEqual(self.refs(uri, 0, 4), [(uri, 0, 4, 9), (uri, 9, 10, 15)])

    def test_variants_fields_and_type_parameters(self):
        uri = self.open(KINDS)
        self.assertEqual(self.defn(uri, 8, 18), {"uri": uri, "range": rng(0, 13, 16)})    # Color.Red, not Light's
        self.assertEqual(self.defn(uri, 11, 14), {"uri": uri, "range": rng(0, 13, 16)})   # in a pattern
        self.assertEqual(self.defn(uri, 9, 16), {"uri": uri, "range": rng(2, 11, 12)})    # P's x, not Q's
        self.assertEqual(self.defn(uri, 15, 17), {"uri": uri, "range": rng(2, 11, 12)})   # in a struct pattern
        self.assertEqual(self.defn(uri, 15, 34), {"uri": uri, "range": rng(15, 20, 21)})  # the match binding
        self.assertEqual(self.hover(uri, 15, 34), "let n")
        self.assertEqual(self.defn(uri, 4, 18), {"uri": uri, "range": rng(4, 10, 11)})    # a type parameter
        self.assertEqual(self.hover(uri, 4, 18), "type parameter T")
        self.assertEqual(self.defn(uri, 11, 52), {"uri": uri, "range": rng(11, 41, 42)})  # a lambda parameter
        self.assertEqual(self.hover(uri, 11, 52), "v: int")
        self.assertEqual(self.refs(uri, 0, 13), [(uri, 0, 13, 16), (uri, 8, 18, 21), (uri, 11, 14, 17)])

    def test_imports(self):
        decoy = self.write("a.my", "pub fun helper() -> int {\n    return 0\n}\n")
        util = self.write("util.my", "// util\npub fun helper() -> int {\n    return 1\n}\n")
        uri = self.open("from util import helper\nfrom util import helper as h\nimport util\n"
                        "from std.fs import read_to_string\n"
                        "fun main() {\n    print(helper() + h() + util.helper())\n}\n")
        at_util = {"uri": _uri(util), "range": rng(1, 8, 14)}
        self.assertEqual(self.defn(uri, 5, 10), at_util)
        self.assertEqual(self.defn(uri, 0, 18), at_util)          # the imported name
        self.assertEqual(self.defn(uri, 5, 21), at_util)          # through an alias
        self.assertEqual(self.defn(uri, 5, 33), at_util)          # through the module
        self.assertEqual(self.defn(uri, 5, 28), {"uri": _uri(util), "range": rng(0, 0, 0)})
        fs = os.path.join(default_stdlib_root(), "std", "fs.my")
        found = self.defn(uri, 3, 22)
        self.assertEqual(found["uri"], _uri(fs))
        with open(fs, encoding="utf-8") as fh:
            line = fh.read().splitlines()[found["range"]["start"]["line"]]
        self.assertIn("fun read_to_string(", line)
        self.assertEqual(self.hover(uri, 5, 21), "pub fun helper() -> int")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestMylaLspScopes(ScopeScenarios, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = myla_tool("tools/lsp/main.my", "lsp")

    def server_command(self) -> list[str]:
        return [self.binary, "--stdlib", default_stdlib_root()]


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestMylaLspScopesSelfHosted(TestMylaLspScopes):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = _self_hosted_build()


TYPED = ("struct P { x: int, y: int }\n"                       # 0
         "impl P {\n"                                           # 1
         "    fun norm(self) -> int {\n"                        # 2
         "        return self.x + self.y\n"                     # 3
         "    }\n"                                              # 4
         "    fun scaled(self, k: int) -> P {\n"                # 5
         "        return P { x: self.x * k, y: self.y * k }\n"  # 6
         "    }\n"                                              # 7
         "}\n"                                                  # 8
         "struct Q { x: int, name: str }\n"                     # 9
         "enum Color { Red, Green }\n"                          # 10
         "fun make() -> P {\n"                                  # 11
         "    return P { x: 1, y: 2 }\n"                        # 12
         "}\n"                                                  # 13
         "fun main() {\n"                                       # 14
         "    let p = make()\n"                                 # 15
         "    let q = Q { x: 1, name: \"q\" }\n"              # 16
         "    let ps = [p]\n"                                   # 17
         "    print(p.norm() + q.x + ps[0].scaled(2).y)\n"      # 18
         "    let c = Color.Red\n"                              # 19
         "}\n")

SIGNATURES = ("pub fun first<T: Eq>(xs: [T]) -> T {\n    return xs[0]\n}\n"
              "pub struct Box<T> { value: T }\n"
              "trait Show {\n    fun show(self) -> str\n}\n"
              "impl<T> Show for Box<T> {\n    fun show(self) -> str {\n        return \"box\"\n    }\n}\n")


class TypeScenarios(LspRequestHelpers):
    """Members through values and completion by the receiver's type, and
    fuller signatures (MYLA-51, step 6)."""

    def defn(self, uri, line, character):
        return self.at("textDocument/definition", uri, line, character)

    def hover(self, uri, line, character):
        h = self.at("textDocument/hover", uri, line, character)
        return h and h["contents"]["value"].removeprefix("```myla\n").removesuffix("\n```")

    def labels(self, uri, line, character):
        return sorted(i["label"] for i in self.at("textDocument/completion", uri, line, character)["items"])

    def change(self, uri, text, version=2):
        self.client.send("textDocument/didChange", {"textDocument": {"uri": uri, "version": version},
                                                     "contentChanges": [{"text": text}]})

    def test_members_through_values(self):
        uri = self.open(TYPED)
        line = TYPED.splitlines()[18]
        self.assertEqual(self.defn(uri, 18, line.index("norm")), {"uri": uri, "range": rng(2, 8, 12)})
        self.assertEqual(self.defn(uri, 18, line.index("q.x") + 2), {"uri": uri, "range": rng(9, 11, 12)})
        self.assertEqual(self.defn(uri, 18, line.index("scaled")), {"uri": uri, "range": rng(5, 8, 14)})
        self.assertEqual(self.defn(uri, 18, line.index(".y") + 1), {"uri": uri, "range": rng(0, 19, 20)})
        self.assertEqual(self.defn(uri, 3, 20), {"uri": uri, "range": rng(0, 11, 12)})      # self.x
        self.assertEqual(self.hover(uri, 18, line.index("norm")), "fun norm(self) -> int")
        self.assertEqual(self.hover(uri, 15, 8), "let p: P")
        self.assertEqual(self.hover(uri, 17, 8), "let ps: [P]")

    def test_references_to_a_field_skip_other_types(self):
        uri = self.open(TYPED)
        found = self.at("textDocument/references", uri, 0, 11, context={"includeDeclaration": False})
        spots = sorted((l["range"]["start"]["line"], l["range"]["start"]["character"]) for l in found)
        line6 = TYPED.splitlines()[6]
        self.assertEqual(spots, [(3, 20), (6, line6.index("x:")), (6, line6.index("self.x") + 5), (12, 15)])

    def test_member_completion_by_type(self):
        uri = self.open(TYPED)
        lines = TYPED.splitlines()
        for typed, expected in (("p.", ["norm", "scaled", "x", "y"]), ("q.", ["name", "x"]),
                                ("Color.", ["Green", "Red"]), ("ps[0].", ["norm", "scaled", "x", "y"]),
                                ("p.sc", ["norm", "scaled", "x", "y"])):
            with self.subTest(typed=typed):
                broken = lines[:18] + ["    print(" + typed] + lines[19:]
                self.change(uri, "\n".join(broken) + "\n")
                self.assertEqual(self.labels(uri, 18, len("    print(" + typed)), expected)

    def test_variants_in_a_pattern(self):
        uri = self.open(TYPED)
        typing = TYPED + "fun code(c: Color) -> int {\n    return match c {\n        Color. => 1,\n        _ => 0,\n    }\n}\n"
        self.change(uri, typing)
        self.assertEqual(self.labels(uri, 23, len("        Color.")), ["Green", "Red"])

    def test_completion_offers_the_locals_in_scope(self):
        uri = self.open(TYPED)
        lines = TYPED.splitlines()
        self.change(uri, "\n".join(lines[:18] + ["    "] + lines[18:]) + "\n")
        labels = self.labels(uri, 18, 4)
        for name in ("p", "q", "ps", "make", "P", "let"):
            self.assertIn(name, labels)
        for name in ("c", "k"):                # declared later, or elsewhere
            self.assertNotIn(name, labels)

    def test_fuller_signatures(self):
        uri = self.open(SIGNATURES)
        symbols = {s["name"]: s for s in self.request("textDocument/documentSymbol", uri)}
        self.assertEqual(symbols["first"]["detail"], "pub fun first<T: Eq>(xs: [T]) -> T")
        self.assertEqual(symbols["Box"]["detail"], "pub struct Box<T>")
        impl = [s for s in self.request("textDocument/documentSymbol", uri) if s["kind"] == 5 or s["detail"].startswith("impl")]
        self.assertEqual([s["detail"] for s in impl if s["detail"].startswith("impl")], ["impl<T> Show for Box<T>"])
        self.assertEqual(impl[-1]["children"][0]["detail"], "fun show(self) -> str")
        self.assertEqual(self.hover(uri, 0, 8), "pub fun first<T: Eq>(xs: [T]) -> T")
        self.assertEqual(self.hover(uri, 3, 11), "pub struct Box<T>")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestMylaLspTypes(TypeScenarios, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = myla_tool("tools/lsp/main.my", "lsp")

    def server_command(self) -> list[str]:
        return [self.binary, "--stdlib", default_stdlib_root()]


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestMylaLspTypesSelfHosted(TestMylaLspTypes):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = _self_hosted_build()


def _corpus() -> list[str]:
    import glob
    return sorted(glob.glob(os.path.join(_REPO, "examples", "*.my")) + glob.glob(os.path.join(_REPO, "selfhost", "*.my"))
                  + glob.glob(os.path.join(_REPO, "tools", "*", "*.my"))
                  + glob.glob(os.path.join(_REPO, "src", "myla", "std", "*.my")))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestResolutionCorpus(unittest.TestCase):
    """`lsp --resolve` over every source in the repository: each name used
    outside a member access that the file declares (as a global, local,
    parameter or type parameter) resolves, a local only after its
    declaration, and no position twice; both builds print the same."""

    def test_the_corpus_resolves(self) -> None:
        from myla.lexer import tokenize
        from myla.tokens import TokenKind
        files = _corpus()
        self.assertGreater(len(files), 50)
        out = subprocess.run([myla_tool("tools/lsp/main.my", "lsp"), "--stdlib", default_stdlib_root(), "--resolve",
                              *files], capture_output=True, text=True, check=True).stdout
        sections = {}
        for line in out.splitlines():
            if line.startswith("file "):
                current = sections.setdefault(line[5:], [])
            else:
                current.append(line)
        self.assertEqual(sorted(sections), files)
        resolved_total = 0
        for path in files:
            with self.subTest(file=os.path.relpath(path, _REPO)):
                lines = sections[path]
                self.assertNotIn("unparsed", lines)
                declared, defs, uses = set(), set(), set()
                for line in lines:
                    parts = line.split()
                    l, rest = parts[1].split(":")
                    pos = (int(l), int(rest.split("-")[0]))
                    if parts[0] == "def":
                        declared.add(parts[3])
                        defs.add(pos)
                    else:
                        self.assertNotIn(pos, uses, line)
                        uses.add(pos)
                        if parts[-1] != "global" and parts[-1] != "module":
                            self.assertEqual(parts[4], path, line)
                            dl, dc = parts[5].split(":")
                            self.assertLess((int(dl), int(dc)), pos, line)
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                source_lines = text.splitlines()
                toks = tokenize(text)
                known = defs | uses
                for k, t in enumerate(toks):
                    if t.kind != TokenKind.IDENT or t.lexeme not in declared:
                        continue
                    if k > 0 and toks[k - 1].kind in (TokenKind.DOT, TokenKind.HASH):
                        continue    # a member, or an attribute's name
                    prefix = source_lines[t.line - 1][:t.column - 1]
                    pos = (t.line - 1, len(prefix.encode("utf-16-le")) // 2)
                    self.assertIn(pos, known, f"{t.lexeme} at {t.line}:{t.column} is not resolved")
                    resolved_total += 1
        self.assertGreater(resolved_total, 30000)

    def test_members_agree_with_the_checker(self) -> None:
        """Where the server resolves `x.f` or `x.m(…)` in an example, it is the
        field or method of the type the Python checker gives `x` (step 6)."""
        import dataclasses, glob
        from myla.lexer import tokenize
        from myla.parser import parse
        from myla.tokens import TokenKind
        from myla.types import EnumType, StructType, check
        from myla import ast
        files = sorted(glob.glob(os.path.join(_REPO, "examples", "*.my")))
        out = subprocess.run([myla_tool("tools/lsp/main.my", "lsp"), "--stdlib", default_stdlib_root(), "--resolve",
                              *files], capture_output=True, text=True, check=True).stdout
        uses = {}
        for line in out.splitlines():
            if line.startswith("file "):
                current = line[5:]
            elif line.startswith("use "):
                parts = line.split()
                l, rest = parts[1].split(":")
                dl, dc = parts[5].split(":")
                uses[(current, int(l), int(rest.split("-")[0]))] = (parts[4], int(dl), int(dc))
        checked = resolved = 0
        for path in files:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            program = parse(tokenize(text))
            check(program)
            toks = tokenize(text)
            # where each struct's fields and each type's methods are declared (1-based)
            fields, methods = {}, {}
            for d in program.decls:
                if isinstance(d, ast.StructDecl):
                    for f in d.fields:
                        fields[(d.name, f.name)] = (f.line, f.column)
                if isinstance(d, ast.ImplDecl) and isinstance(d.target, ast.TypeRef):
                    for m in d.methods:
                        methods[(d.target.name, m.name)] = m.line
            accesses = []

            def walk(node):
                if isinstance(node, ast.FieldAccess):
                    accesses.append(node)
                if dataclasses.is_dataclass(node):
                    for f in dataclasses.fields(node):
                        walk(getattr(node, f.name))
                elif isinstance(node, list):
                    for x in node:
                        walk(x)
            walk(program.decls)
            lines = text.splitlines()
            for node in accesses:
                t = getattr(node.target, "resolved_type", None)
                if not isinstance(t, (StructType, EnumType)) or not lines[node.line - 1].isascii():
                    continue
                # the member's token: the first `.name` from the access on
                k = next((i for i, tk in enumerate(toks) if (tk.line, tk.column) >= (node.line, node.column)
                          and tk.kind == TokenKind.IDENT and tk.lexeme == node.field_name
                          and toks[i - 1].kind == TokenKind.DOT), None)
                if k is None:
                    continue
                key = (t.name, node.field_name)
                if key not in fields and key not in methods:
                    continue
                checked += 1
                found = uses.get((path, toks[k].line - 1, toks[k].column - 1))
                if found is None:
                    continue
                resolved += 1
                with self.subTest(file=os.path.basename(path), line=toks[k].line, member=node.field_name):
                    self.assertEqual(found[0], path)
                    if key in fields:
                        self.assertEqual((found[1], found[2]), (fields[key][0] - 1, fields[key][1] - 1))
                    else:
                        self.assertEqual(found[1], methods[key] - 1)
        self.assertGreater(checked, 60)
        self.assertGreater(resolved, checked * 0.9, f"{resolved} of {checked} resolved")
        print(f"members: {resolved} of {checked} resolved", file=sys.stderr)

    def test_both_builds_agree(self) -> None:
        argv = ["--stdlib", default_stdlib_root(), "--resolve", *_corpus()]
        by_python = subprocess.run([myla_tool("tools/lsp/main.my", "lsp"), *argv], capture_output=True, text=True,
                                   check=True).stdout
        by_selfhost = subprocess.run([_self_hosted_build(), *argv], capture_output=True, text=True, check=True).stdout
        self.assertGreater(len(by_python.splitlines()), 30000)
        self.assertEqual(by_selfhost, by_python)


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


def _node_strips_types() -> bool:
    import shutil
    if shutil.which("node") is None:
        return False
    return subprocess.run(["node", "--experimental-strip-types", "-e", "0"], capture_output=True).returncode == 0


_EXTENSION = os.path.join(_REPO, "vscode-extension", "myla")


@unittest.skipUnless(CAN_BUILD_NATIVE and _node_strips_types(), "needs a native toolchain and node 22.6+")
class TestExtensionStartsTheServer(unittest.TestCase):
    """The VS Code extension's server command (`vscode-extension/myla/src/
    server.ts`, run by node with its types stripped): the Myla server, from
    `myla.serverPath` or the repository's build/, or why there is none; and the
    command it picks serves (MYLA-80 step 7, MYLA-83)."""

    def choose(self, settings: dict, existing: list) -> dict | None:
        script = ("import { chooseServer } from " + json.dumps(os.path.join(_EXTENSION, "src", "server.ts")) + ";\n"
                  "const [settings, existing] = JSON.parse(process.argv[1]);\n"
                  "console.log(JSON.stringify(chooseServer(settings, (p) => existing.includes(p)) ?? null));\n")
        out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", script,
                              json.dumps([settings, existing])], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def settings(self, **over) -> dict:
        s = {"serverPath": "", "compilerEntry": "/r/myla.py"}
        s.update(over)
        return s

    def test_the_built_server(self):
        c = self.choose(self.settings(), ["/r/build/myla-lsp", "/r/src/myla/std"])
        self.assertEqual((c["command"], c["args"]), ("/r/build/myla-lsp", ["--stdlib", "/r/src/myla"]))

    def test_a_configured_binary(self):
        c = self.choose(self.settings(serverPath="/opt/myla-lsp", compilerEntry=None), ["/opt/myla-lsp"])
        self.assertEqual((c["command"], c["args"]), ("/opt/myla-lsp", []))

    def test_no_server_says_what_to_do(self):
        # the Python server it fell back to is gone (MYLA-83)
        self.assertIn("scripts/bootstrap.sh", self.choose(self.settings(), [])["missing"])
        self.assertIn("myla.serverPath", self.choose(self.settings(compilerEntry=None), [])["missing"])

    def test_the_chosen_command_serves(self):
        binary = myla_tool("tools/lsp/main.my", "lsp")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "build"))
            os.symlink(binary, os.path.join(tmp, "build", "myla-lsp"))
            os.symlink(os.path.join(_REPO, "src"), os.path.join(tmp, "src"))
            entry = os.path.join(tmp, "myla.py")
            c = self.choose(self.settings(compilerEntry=entry),
                            [os.path.join(tmp, "build", "myla-lsp"), os.path.join(tmp, "src", "myla", "std")])
            client = _Client([c["command"], *c["args"]])
            self.addCleanup(client.close)
            rid = client.send("initialize", {"processId": None, "rootUri": _uri(tmp), "capabilities": {}}, request=True)
            self.assertIn("completionProvider", client.response(rid)["result"]["capabilities"])


class TestOwnTests(unittest.TestCase):
    def test_the_server_s_own_tests_pass(self) -> None:
        # server.my imports every other module of tools/lsp (and std.json, std.num)
        import sys
        proc = subprocess.run([sys.executable, os.path.join(_REPO, "myla.py"), "test",
                               os.path.join(_REPO, "tools", "lsp", "server.my")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
