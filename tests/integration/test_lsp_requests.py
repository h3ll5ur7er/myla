"""End-to-end tests of the language server's requests over stdio JSON-RPC:
document symbols, definition, references, hover and completion.

The scenarios (`LspRequestScenarios`) are the cases of tests/unit/
test_lsp_features.py, sent as requests. They run against the Python server
here (needs the `lsp` extra, pygls) and against the Myla server in
tests/burn/test_lsp.py (MYLA-80).
"""
import os
import shutil
import sys
import tempfile
import unittest

from tests.integration.test_lsp_diagnostics import HAVE_PYGLS, _REPO, _Client, _uri


def rng(line, start, end):
    return {"start": {"line": line, "character": start}, "end": {"line": line, "character": end}}


SOURCE = ("fun un(n: int) -> int {\n"
          "    return n\n"
          "}\n"
          "fun main() {\n"
          "    // un in a comment\n"
          "    print(un(1) + un(2))\n"
          "    print(\"un\")\n"
          "}\n")

COMPLETION_SOURCE = ("struct P { x: int }\nenum E { A, B }\nfun get(p: P) -> int {\n    return p.x\n}\n"
                     "fun main() {\n    let p = P { x: 1 }\n    print(p.x)\n}\n")


class LspRequestScenarios:
    """A subclass names the server (`server_command`) and mixes in
    unittest.TestCase. Each test runs in a workspace of its own."""

    def server_command(self) -> list:
        raise NotImplementedError

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="myla_lsp_req_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.client = _Client(self.server_command())
        self.addCleanup(self.client.close)
        rid = self.client.send("initialize", {"processId": None, "rootUri": _uri(self.root),
                                              "capabilities": {}}, request=True)
        self.capabilities = self.client.response(rid)["result"]["capabilities"]
        self.client.send("initialized", {})

    def write(self, name, text):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def open(self, text, name="doc.my"):
        """Write `text` to the workspace and open it; its URI."""
        path = self.write(name, text)
        self.client.send("textDocument/didOpen", {"textDocument": {
            "uri": _uri(path), "languageId": "myla", "version": 1, "text": text}})
        return _uri(path)

    def request(self, method, uri, **params):
        params["textDocument"] = {"uri": uri}
        rid = self.client.send(method, params, request=True)
        reply = self.client.response(rid)
        self.assertNotIn("error", reply)
        return reply["result"]

    def at(self, method, uri, line, character, **params):
        return self.request(method, uri, position={"line": line, "character": character}, **params)

    def symbols(self, text, name="doc.my"):
        return self.request("textDocument/documentSymbol", self.open(text, name))

    def flat(self, symbols):
        out = {}
        for s in symbols:
            out.setdefault(s["name"], s)
            out.update({k: v for k, v in self.flat(s.get("children", [])).items() if k not in out})
        return out

    # -- capabilities --------------------------------------------------------

    def test_capabilities(self):
        for cap in ("documentSymbolProvider", "definitionProvider", "referencesProvider", "hoverProvider"):
            self.assertTrue(self.capabilities.get(cap), cap)
        self.assertIn("completionProvider", self.capabilities)

    # -- document symbols (MYLA-48: the selection range is the name) ----------

    def test_short_names_inside_the_keyword(self):
        syms = self.flat(self.symbols("fun un() {}\nconst t: int = 1\nstruct S { s: int }\nenum E { E }\n"))
        self.assertEqual(syms["un"]["selectionRange"], rng(0, 4, 6))
        self.assertEqual(syms["t"]["selectionRange"], rng(1, 6, 7))
        self.assertEqual(syms["S"]["selectionRange"], rng(2, 7, 8))
        self.assertEqual(syms["s"]["selectionRange"], rng(2, 11, 12))

    def test_variant_named_like_its_enum(self):
        [enum] = self.symbols("enum E { E, F }\n")
        self.assertEqual(enum["selectionRange"], rng(0, 5, 6))
        self.assertEqual([(v["name"], v["selectionRange"]) for v in enum["children"]],
                         [("E", rng(0, 9, 10)), ("F", rng(0, 12, 13))])

    def test_generic_declarations(self):
        syms = self.flat(self.symbols(
            "fun id<T>(x: T) -> T {\n    return x\n}\n"
            "struct Box<T> { v: T }\n"
            "trait Tr<T> {\n    fun get(self) -> T\n}\n"
            "impl<T> Box<T> {\n    fun un(self) -> T {\n        return self.v\n    }\n}\n"
            "typealias ty = int\n"))
        self.assertEqual(syms["id"]["selectionRange"], rng(0, 4, 6))
        self.assertEqual(syms["Box"]["selectionRange"], rng(3, 7, 10))
        self.assertEqual(syms["Tr"]["selectionRange"], rng(4, 6, 8))
        self.assertEqual(syms["get"]["selectionRange"], rng(5, 8, 11))
        self.assertEqual(syms["Box<T>"]["selectionRange"], rng(7, 8, 11))   # the impl
        self.assertEqual(syms["un"]["selectionRange"], rng(8, 8, 10))
        self.assertEqual(syms["ty"]["selectionRange"], rng(12, 10, 12))

    def test_impl_selects_its_target(self):
        impl = self.symbols("trait G<T> {\n    fun g(self) -> T\n}\n"
                            "impl G<int32> for int32 {\n    fun g(self) -> int32 {\n        return self\n    }\n}\n")[1]
        self.assertEqual((impl["name"], impl["selectionRange"]), ("int32", rng(3, 18, 23)))

    def test_attributes_and_pub_before_the_keyword(self):
        syms = self.flat(self.symbols("#test(2)[4]\npub fun f(f: int) -> int {\n    return f * 2\n}\n"))
        self.assertEqual(syms["f"]["selectionRange"], rng(1, 8, 9))

    def test_names_after_astral_characters(self):
        syms = self.flat(self.symbols('const A: str = "😀"\nconst B: int = 1\n'))
        self.assertEqual(syms["B"]["selectionRange"], rng(1, 6, 7))
        syms = self.flat(self.symbols('struct P { a: str }\nfun f() -> P {\n    return P { a: "😀" }\n}\n',
                                      "doc2.my"))
        self.assertEqual(syms["f"]["selectionRange"], rng(1, 4, 5))

    def test_declarations_separated_by_semicolons(self):
        syms = self.flat(self.symbols("const A: int = 1; const B: int = A\nfun f() {}; fun g() {}\n"))
        self.assertEqual(syms["A"]["selectionRange"], rng(0, 6, 7))
        self.assertEqual(syms["B"]["selectionRange"], rng(0, 24, 25))
        self.assertEqual(syms["g"]["selectionRange"], rng(1, 16, 17))

    def test_outline(self):
        source = ("struct P { x: int, y: int }\nenum Sh { Dot, Box(int) }\n"
                  "trait Area {\n    fun area(self) -> int\n}\n"
                  "impl Area for P {\n    fun area(self) -> int {\n        return self.x\n    }\n}\n"
                  "fun main() {}\n")
        outline = [(s["name"], s["kind"], [(c["name"], c["kind"]) for c in s.get("children", [])])
                   for s in self.symbols(source)]
        self.assertEqual(outline, [
            ("P", 23, [("x", 8), ("y", 8)]),
            ("Sh", 10, [("Dot", 22), ("Box", 22)]),
            ("Area", 11, [("area", 6)]),
            ("P", 19, [("area", 6)]),
            ("main", 12, []),
        ])
        details = {s["name"]: s.get("detail") for s in self.symbols(source)}
        self.assertEqual(details["main"], "fun main()")

    def test_a_parse_error_gives_no_symbols(self):
        self.assertEqual(self.symbols("fun (\n"), [])

    # -- definition and references --------------------------------------------

    def test_definition_jumps_to_the_name(self):
        uri = self.open(SOURCE)
        self.assertEqual(self.at("textDocument/definition", uri, 5, 11), {"uri": uri, "range": rng(0, 4, 6)})

    def test_definition_falls_back_to_the_workspace(self):
        other = self.write("other.my", "fun helper() {}\n\n\npub fun other() {}\n")
        uri = self.open("fun main() {\n    other()\n}\n")
        self.assertEqual(self.at("textDocument/definition", uri, 1, 5),
                         {"uri": _uri(other), "range": rng(3, 8, 13)})
        self.assertIsNone(self.at("textDocument/definition", uri, 1, 0))      # not on an identifier

    def test_references_skip_comments_and_strings(self):
        uri = self.open(SOURCE)
        refs = self.at("textDocument/references", uri, 5, 11, context={"includeDeclaration": True})
        self.assertEqual([r["range"] for r in refs], [rng(0, 4, 6), rng(5, 10, 12), rng(5, 18, 20)])

    def test_references_without_the_declaration(self):
        uri = self.open(SOURCE)
        refs = self.at("textDocument/references", uri, 5, 11, context={"includeDeclaration": False})
        self.assertEqual([r["range"] for r in refs], [rng(5, 10, 12), rng(5, 18, 20)])

    def test_references_include_other_files_once(self):
        other = self.write("other.my", "fun g() {\n  un(3)\n}\n")
        uri = self.open(SOURCE)
        refs = self.at("textDocument/references", uri, 5, 11, context={"includeDeclaration": True})
        self.assertEqual(len(refs), 4)                     # doc.my is in the workspace too: no duplicates
        self.assertIn({"uri": _uri(other), "range": rng(1, 2, 4)}, refs)

    # -- hover -----------------------------------------------------------------

    def test_hover(self):
        uri = self.open("struct P { x: int }\nenum E { A, B(int) }\nconst N: int = 3\n"
                        "fun get(p: P) -> int {\n    return p.x + N\n}\n")
        def hover(line, character):
            h = self.at("textDocument/hover", uri, line, character)
            return None if h is None else h["contents"]["value"]
        self.assertEqual(hover(3, 5), "```myla\nfun get(p: P) -> int\n```")
        self.assertEqual(hover(3, 11), "```myla\nstruct P\n```")
        self.assertEqual(hover(4, 13), "```myla\nx: int\n```")
        self.assertEqual(hover(4, 17), "```myla\nconst N: int\n```")
        self.assertEqual(hover(1, 12), "```myla\nB(int)\n```")
        self.assertIsNone(hover(4, 6))                     # `return`

    # -- completion ------------------------------------------------------------

    def labels(self, uri, line, character):
        result = self.at("textDocument/completion", uri, line, character)
        return {item["label"] for item in result["items"]}

    def test_members_after_a_dot(self):
        uri = self.open(COMPLETION_SOURCE)
        self.assertEqual(self.labels(uri, 7, 12), {"x", "A", "B"})

    def test_keywords_and_declarations_elsewhere(self):
        uri = self.open(COMPLETION_SOURCE)
        labels = self.labels(uri, 6, 4)
        self.assertLessEqual({"fun", "match", "float64", "char", "P", "E", "get", "main"}, labels)
        self.assertNotIn("x", labels)

    def test_member_access_after_astral_characters(self):
        uri = self.open('fun main() {\n    let s = "😀" + p.\n    let t = "😀" + q\n}\n')
        result = self.at("textDocument/completion", uri, 1, 21)    # just after `p.`
        self.assertTrue(all(item.get("kind") != 14 for item in result["items"]))
        uri = self.open('fun main() {\n    let s = "😀" .x\n}\n', "doc2.my")
        self.assertIn("fun", self.labels(uri, 1, 17))               # before the `.`


@unittest.skipUnless(HAVE_PYGLS, "needs the lsp extra (pygls)")
class TestLspRequests(LspRequestScenarios, unittest.TestCase):
    def server_command(self):
        return [sys.executable, os.path.join(_REPO, "myla.py"), "lsp"]


if __name__ == "__main__":
    unittest.main()
