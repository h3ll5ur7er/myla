"""The language server's scenarios over stdio JSON-RPC, shared by the burn
tests of the server written in Myla (tests/burn/test_lsp.py, MYLA-80): a
protocol client (`_Client`), the diagnostics scenarios (`LspScenarios`) and
the request scenarios (`LspRequestScenarios`, the cases of the retired Python
server's unit tests). A subclass names the server (`server_command`) and mixes
in unittest.TestCase. Until MYLA-83 these ran against the Python server too.
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


class _Client:
    """A minimal LSP client: framed JSON-RPC over the server's stdin/stdout. A
    reader thread queues incoming messages, so a missing one fails the test
    after a timeout instead of hanging it."""

    TIMEOUT = 10

    def __init__(self, argv):
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL)
        self.next_id = 1
        self.messages: queue.Queue = queue.Queue()
        threading.Thread(target=self._read_all, daemon=True).start()

    def send(self, method, params, request=False):
        """Send a notification, or a request (returns its id)."""
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if request:
            msg["id"] = self.next_id
            self.next_id += 1
        self.send_raw(json.dumps(msg).encode())
        return msg.get("id")

    def send_raw(self, body: bytes):
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.proc.stdin.flush()

    def _read_all(self):
        try:
            while True:
                length = 0
                while True:
                    line = self.proc.stdout.readline()
                    if line == b"":
                        return
                    if line == b"\r\n":
                        break
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":")[1])
                self.messages.put(json.loads(self.proc.stdout.read(length)))
        except (OSError, ValueError):   # the pipe closed under us
            return

    def receive(self):
        try:
            return self.messages.get(timeout=self.TIMEOUT)
        except queue.Empty:
            raise AssertionError("no message from the language server") from None

    def response(self, request_id):
        """The response to request `request_id` (skipping notifications)."""
        while True:
            msg = self.receive()
            if "method" not in msg and msg.get("id") == request_id:
                return msg

    def diagnostics(self, count, full=False):
        """The next `count` publishDiagnostics notifications, as {uri: [message]}
        (with `full`, {uri: [diagnostic]})."""
        got = {}
        while len(got) < count:
            msg = self.receive()
            if msg.get("method") == "textDocument/publishDiagnostics":
                p = msg["params"]
                got[p["uri"]] = p["diagnostics"] if full else [d["message"] for d in p["diagnostics"]]
        return got

    def close(self):
        self.proc.kill()
        self.proc.wait()
        self.proc.stdin.close()
        self.proc.stdout.close()


def _uri(path):
    return "file://" + os.path.realpath(path)


class LspScenarios:
    """Diagnostics scenarios; a subclass names the server (`server_command`)
    and mixes in unittest.TestCase."""

    def server_command(self) -> list[str]:
        raise NotImplementedError

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="myla_lsp_")
        self.main = os.path.join(self.root, "main.my")
        self.bad = os.path.join(self.root, "bad.my")
        self.main_src = "from .bad import f\nfun main() {\n    print(f())\n}\n"
        with open(self.main, "w") as fh:
            fh.write(self.main_src)
        with open(self.bad, "w") as fh:
            fh.write("pub fun f() -> int {\n    return \"oops\"\n}\n")
        self.client = _Client(self.server_command())
        self.addCleanup(self.client.close)
        rid = self.client.send("initialize", {"processId": None, "rootUri": _uri(self.root),
                                              "capabilities": {}}, request=True)
        reply = self.client.response(rid)
        self.assertIn("result", reply)
        self.capabilities = reply["result"]["capabilities"]
        self.client.send("initialized", {})

    def open(self, path, text):
        self.client.send("textDocument/didOpen", {"textDocument": {
            "uri": _uri(path), "languageId": "myla", "version": 1, "text": text}})

    def change(self, path, text, version=2):
        self.client.send("textDocument/didChange", {
            "textDocument": {"uri": _uri(path), "version": version},
            "contentChanges": [{"text": text}]})

    def test_an_imported_module_error_is_published_for_that_module(self):
        # MYLA-10: the error belongs to bad.my, not to the open main.my
        self.open(self.main, self.main_src)
        got = self.client.diagnostics(2)
        self.assertEqual(got[_uri(self.main)], [])
        self.assertEqual(len(got[_uri(self.bad)]), 1)
        self.assertIn("return type mismatch", got[_uri(self.bad)][0])

    def test_fixing_the_module_clears_its_diagnostic(self):
        self.open(self.main, self.main_src)
        self.client.diagnostics(2)
        self.open(self.bad, "pub fun f() -> int {\n    return 1\n}\n")
        self.assertEqual(self.client.diagnostics(1), {_uri(self.bad): []})
        self.client.send("textDocument/didSave", {"textDocument": {"uri": _uri(self.main)}})
        got = self.client.diagnostics(2)   # main.my, and bad.my cleared
        self.assertEqual(got, {_uri(self.main): [], _uri(self.bad): []})

    def test_the_unsaved_text_is_checked(self):
        self.open(self.bad, "pub fun f() -> int {\n    return 1\n}\n")
        self.assertEqual(self.client.diagnostics(1), {_uri(self.bad): []})
        self.change(self.bad, "pub fun f() -> int {\n    return true\n}\n")
        got = self.client.diagnostics(1, full=True)[_uri(self.bad)]
        self.assertEqual(len(got), 1)
        # under the whole `return true`, as the command line underlines it (MYLA-65)
        self.assertEqual(got[0]["range"], {"start": {"line": 1, "character": 4},
                                           "end": {"line": 1, "character": 15}})
        self.assertEqual((got[0]["severity"], got[0]["source"], got[0]["code"]), (1, "myla", "type"))

    def test_other_open_buffers_are_used_unsaved(self):
        # MYLA-49: bad.my is fixed in the editor but not on disk
        self.open(self.bad, "pub fun f() -> int {\n    return 1\n}\n")
        self.client.diagnostics(1)
        self.open(self.main, self.main_src)
        self.assertEqual(self.client.diagnostics(1), {_uri(self.main): []})

    def test_ranges_count_utf16_units(self):
        src = 'fun main() {\n    let s = "😀é"; let x: int = s\n}\n'
        self.open(self.main, src)
        got = self.client.diagnostics(1, full=True)[_uri(self.main)]
        self.assertEqual(len(got), 1)
        # the second `let` statement, from code point 18; "😀" is two UTF-16 units
        self.assertEqual(got[0]["range"], {"start": {"line": 1, "character": 19},
                                           "end": {"line": 1, "character": 33}})

    def test_a_parse_error(self):
        self.open(self.main, "fun main() {\n    let = 1\n}\n")
        got = self.client.diagnostics(1, full=True)[_uri(self.main)]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["code"], "parse")
        self.assertEqual(got[0]["range"]["start"], {"line": 1, "character": 8})

    def test_every_error_is_published(self):
        # every function is checked on its own (MYLA-65, D80)
        src = "fun f() -> int {\n    return \"s\"\n}\nfun main() {\n    let x: int = true\n}\n"
        self.open(self.main, src)
        got = self.client.diagnostics(1, full=True)[_uri(self.main)]
        self.assertEqual([(d["range"]["start"]["line"], d["code"]) for d in got], [(1, "type"), (4, "type")])

    def test_every_parse_error_is_published(self):
        self.open(self.main, "fun main() {\n    let = 1\n    print(1 +)\n}\n")
        got = self.client.diagnostics(1, full=True)[_uri(self.main)]
        self.assertEqual([(d["range"]["start"]["line"], d["code"]) for d in got], [(1, "parse"), (2, "parse")])

    def test_errors_in_two_files_are_published_for_each(self):
        self.open(self.main, "from .bad import f\nfun main() {\n    print(f())\n    let x: int = true\n}\n")
        got = self.client.diagnostics(2)
        self.assertEqual(len(got[_uri(self.main)]), 1)
        self.assertIn("cannot assign", got[_uri(self.main)][0])
        self.assertEqual(len(got[_uri(self.bad)]), 1)
        self.assertIn("return type mismatch", got[_uri(self.bad)][0])

    def test_an_unknown_request_is_an_error(self):
        rid = self.client.send("myla/noSuchThing", {}, request=True)
        self.assertEqual(self.client.response(rid)["error"]["code"], -32601)

    def test_shutdown_and_exit(self):
        rid = self.client.send("shutdown", None, request=True)
        self.assertIsNone(self.client.response(rid)["result"])
        self.client.send("exit", None)
        self.assertEqual(self.client.proc.wait(10), 0)


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


class LspRequestHelpers:
    """Starts the server named by `server_command` in a workspace of its own
    (`self.root`) for each test, with helpers to open documents and send
    requests. Mixed in with unittest.TestCase."""

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



class LspRequestScenarios(LspRequestHelpers):
    """The cases of tests/unit/test_lsp_features.py as requests."""

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

    # the receiver's members (MYLA-80 step 6)
    MEMBERS_OF_P = {"x"}

    def test_members_after_a_dot(self):
        uri = self.open(COMPLETION_SOURCE)
        self.assertEqual(self.labels(uri, 7, 12), self.MEMBERS_OF_P)

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


GEO = "// geo\npub fun area(n: int) -> int {\n    return n * n\n}\n"
SHAPES = ("from .geo import area\npub struct Square { side: int }\n"
          "pub fun square_area(s: Square) -> int {\n    return area(s.side)\n}\n")
APP_MAIN = ("import geo\nfrom geo.shapes import Square, square_area\nfun main() {\n"
            "    print(geo.area(2) + square_area(Square { side: 3 }))\n}\n")


class ProjectScenarios(LspRequestHelpers):
    """Documents inside a project (MYLA-97): the workspace root holds
    `myla.toml` for a package `app` with a path dependency `geo`, which lies
    outside the workspace. A document is checked and resolved as `myla check`
    loads it: with the project's packages and `src/` as the project root."""

    def setUp(self):
        super().setUp()
        self.geo = tempfile.mkdtemp(prefix="myla_lsp_geo_")
        self.addCleanup(shutil.rmtree, self.geo, True)
        self.write_in(self.geo, "myla.toml", '[package]\nname = "geo"\nversion = "0.1.0"\n')
        self.write_in(self.geo, "src/geo.my", GEO)
        self.write_in(self.geo, "src/shapes.my", SHAPES)
        self.manifest = self.write("myla.toml", '[package]\nname = "app"\nversion = "0.1.0"\n\n[dependencies]\n'
                                   'geo = { path = "%s" }\n' % os.path.relpath(self.geo, self.root))

    def write_in(self, base, name, text):
        path = os.path.join(base, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def open_src(self, name, text):
        os.makedirs(os.path.dirname(os.path.join(self.root, name)), exist_ok=True)
        return self.open(text, name)

    def geo_file(self, name):
        return _uri(os.path.join(self.geo, "src", name))

    def labels(self, uri, line, character):
        return sorted(i["label"] for i in self.at("textDocument/completion", uri, line, character)["items"])

    def test_imports_of_a_dependency_check_clean(self):
        uri = self.open_src("src/main.my", APP_MAIN)
        self.assertEqual(self.client.diagnostics(1), {uri: []})

    def test_an_error_in_a_dependency_is_published_for_its_file(self):
        self.write_in(self.geo, "src/shapes.my", SHAPES.replace("return area(s.side)", 'return "side"'))
        uri = self.open_src("src/main.my", APP_MAIN)
        got = self.client.diagnostics(2)
        self.assertEqual(got[uri], [])
        [msg] = got[self.geo_file("shapes.my")]
        self.assertIn("return type mismatch", msg)

    def test_definition_and_hover_reach_into_the_dependency(self):
        uri = self.open_src("src/main.my", APP_MAIN)
        self.assertEqual(self.at("textDocument/definition", uri, 3, 15),
                         {"uri": self.geo_file("geo.my"), "range": rng(1, 8, 12)})
        self.assertEqual(self.at("textDocument/definition", uri, 1, 33),
                         {"uri": self.geo_file("shapes.my"), "range": rng(2, 8, 19)})
        self.assertEqual(self.at("textDocument/definition", uri, 3, 11),
                         {"uri": self.geo_file("geo.my"), "range": rng(0, 0, 0)})      # the module
        hover = self.at("textDocument/hover", uri, 3, 15)["contents"]["value"]
        self.assertEqual(hover, "```myla\npub fun area(n: int) -> int\n```")

    def test_references_include_the_dependency_s_files(self):
        uri = self.open_src("src/main.my", APP_MAIN)
        found = self.at("textDocument/references", uri, 3, 15, context={"includeDeclaration": True})
        spots = sorted((l["uri"], l["range"]["start"]["line"], l["range"]["start"]["character"]) for l in found)
        self.assertEqual(spots, sorted([(uri, 3, 14), (self.geo_file("geo.my"), 1, 8),
                                        (self.geo_file("shapes.my"), 0, 17), (self.geo_file("shapes.my"), 3, 11)]))

    def test_completion_after_a_package_module(self):
        uri = self.open_src("src/main.my", APP_MAIN)
        self.client.send("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2}, "contentChanges": [
            {"text": APP_MAIN.replace("print(geo.area(2) + square_area(Square { side: 3 }))", "print(geo.")}]})
        self.assertEqual(self.labels(uri, 3, len("    print(geo.")), ["area"])

    def test_a_nested_file_imports_from_src(self):
        helpers = self.write_in(self.root, "src/helpers.my", "pub fun double(n: int) -> int {\n    return n * 2\n}\n")
        uri = self.open_src("src/util/round.my", "import helpers\nimport geo\npub fun twice(n: int) -> int {\n"
                                                 "    return helpers.double(geo.area(n))\n}\n")
        self.assertEqual(self.client.diagnostics(1), {uri: []})
        self.assertEqual(self.at("textDocument/definition", uri, 3, 20),
                         {"uri": _uri(helpers), "range": rng(0, 8, 14)})

    def test_a_checked_out_git_dependency(self):
        commit = "0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c"
        checkout = os.path.join(self.root, ".myla", "deps", "color-" + commit)
        self.write_in(checkout, "myla.toml", '[package]\nname = "color"\nversion = "1.0.0"\n')
        color = self.write_in(checkout, "src/color.my", "pub fun red() -> int {\n    return 1\n}\n")
        self.write("myla.toml", '[package]\nname = "app"\nversion = "0.1.0"\n\n[dependencies]\n'
                                'color = { git = "https://example.org/color.git" }\n')
        self.write("myla.lock", 'version = 1\n\n[git.color]\nurl = "https://example.org/color.git"\n'
                                'commit = "%s"\n' % commit)
        uri = self.open_src("src/main.my", "import color\nfun main() {\n    print(color.red())\n}\n")
        self.assertEqual(self.client.diagnostics(1), {uri: []})
        self.assertEqual(self.at("textDocument/definition", uri, 2, 16),
                         {"uri": _uri(color), "range": rng(0, 8, 11)})

    def test_a_git_dependency_that_is_not_checked_out(self):
        # the server never fetches: the import fails, and the manifest says why
        self.write("myla.toml", '[package]\nname = "app"\nversion = "0.1.0"\n\n[dependencies]\n'
                                'geo = { path = "%s" }\n' % os.path.relpath(self.geo, self.root)
                                + 'color = { git = "https://example.org/color.git" }\n')
        self.write("myla.lock", 'version = 1\n\n[git.color]\nurl = "https://example.org/color.git"\n'
                                'commit = "0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c"\n')
        uri = self.open_src("src/main.my", "import color\nimport geo\nfun main() {\n    print(color.red() + geo.area(1))\n}\n")
        got = self.client.diagnostics(2, full=True)
        self.assertEqual([d["message"] for d in got[uri]], ["cannot resolve import 'color'"])   # geo still resolves
        [d] = got[_uri(self.manifest)]
        self.assertEqual(d["message"], "dependency 'color' is not checked out: run `myla fetch`")
        self.assertEqual(d["range"], rng(6, 0, 5))  # under its key
        self.assertFalse(os.path.exists(os.path.join(self.root, ".myla")))

    def test_a_manifest_error_is_published_for_the_manifest(self):
        self.write("myla.toml", '[package]\nname = "app"\n')
        uri = self.open_src("src/main.my", "fun main() {\n    print(1)\n}\n")
        got = self.client.diagnostics(2, full=True)
        self.assertEqual(got[uri], [])              # checked as a single file
        [d] = got[_uri(self.manifest)]
        self.assertEqual((d["message"], d["code"]), ("missing 'version' in [package]", "manifest"))
        self.assertEqual(d["range"], rng(0, 0, 9))  # under `[package]`
        # fixed on disk: the open documents are checked again
        self.write("myla.toml", '[package]\nname = "app"\nversion = "0.1.0"\n')
        self.client.send("workspace/didChangeWatchedFiles", {"changes": [{"uri": _uri(self.manifest), "type": 2}]})
        self.assertEqual(self.client.diagnostics(2), {uri: [], _uri(self.manifest): []})


class WorkspaceScanScenarios(LspRequestHelpers):
    """The workspace's files are listed with std.fs (MYLA-97), skipping the
    directories that hold builds, fetched dependencies and tools' data."""

    def test_the_scan_skips_build_and_dependency_directories(self):
        for d in ("sub/deeper", "build", ".myla/deps/x/src", ".git", "node_modules"):
            os.makedirs(os.path.join(self.root, d), exist_ok=True)
        self.write("sub/deeper/ok.my", "pub fun in_sub() {}\n")
        self.write("build/gen.my", "pub fun in_build() {}\n")
        self.write(".myla/deps/x/src/x.my", "pub fun in_deps() {}\n")
        self.write(".git/hook.my", "pub fun in_git() {}\n")
        self.write("node_modules/mod.my", "pub fun in_node() {}\n")
        line = "    in_sub(); in_build(); in_deps(); in_git(); in_node()"
        uri = self.open("fun main() {\n" + line + "\n}\n")
        self.assertEqual(self.at("textDocument/definition", uri, 1, 4),
                         {"uri": _uri(os.path.join(self.root, "sub", "deeper", "ok.my")), "range": rng(0, 8, 14)})
        for name in ("in_build", "in_deps", "in_git", "in_node"):
            with self.subTest(name=name):
                self.assertIsNone(self.at("textDocument/definition", uri, 1, line.index(name)))

    def test_files_are_listed_in_sorted_order(self):
        # the first declaration of a name in sorted path order wins
        os.makedirs(os.path.join(self.root, "a"))
        self.write("a/z.my", "\npub fun twin() {}\n")
        self.write("a.my", "pub fun twin() {}\n")
        self.write("b.my", "\n\npub fun twin() {}\n")
        uri = self.open("fun main() {\n    twin()\n}\n", "main.my")
        self.assertEqual(self.at("textDocument/definition", uri, 1, 4),
                         {"uri": _uri(os.path.join(self.root, "a.my")), "range": rng(0, 8, 12)})
