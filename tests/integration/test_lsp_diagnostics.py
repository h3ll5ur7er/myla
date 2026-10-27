"""End-to-end test of the language server's diagnostics over stdio JSON-RPC.

The scenarios (`LspScenarios`) run against the Python server here, which needs
the optional `lsp` extra (pygls) and is skipped without it, and against the
Myla server in tests/burn/test_lsp.py (MYLA-80).
"""
import importlib.util
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
HAVE_PYGLS = importlib.util.find_spec("pygls") is not None


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
        # at `return`, the squiggle as wide as the word
        self.assertEqual(got[0]["range"], {"start": {"line": 1, "character": 4},
                                           "end": {"line": 1, "character": 10}})
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
        # at the second `let`, code point 18; "😀" is two UTF-16 units
        self.assertEqual(got[0]["range"], {"start": {"line": 1, "character": 19},
                                           "end": {"line": 1, "character": 22}})

    def test_a_parse_error(self):
        self.open(self.main, "fun main() {\n    let = 1\n}\n")
        got = self.client.diagnostics(1, full=True)[_uri(self.main)]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["code"], "parse")
        self.assertEqual(got[0]["range"]["start"], {"line": 1, "character": 8})

    def test_an_unknown_request_is_an_error(self):
        rid = self.client.send("myla/noSuchThing", {}, request=True)
        self.assertEqual(self.client.response(rid)["error"]["code"], -32601)

    def test_shutdown_and_exit(self):
        rid = self.client.send("shutdown", None, request=True)
        self.assertIsNone(self.client.response(rid)["result"])
        self.client.send("exit", None)
        self.assertEqual(self.client.proc.wait(10), 0)


@unittest.skipUnless(HAVE_PYGLS, "needs the lsp extra (pygls)")
class TestLspDiagnostics(LspScenarios, unittest.TestCase):
    def server_command(self):
        return [sys.executable, os.path.join(_REPO, "myla.py"), "lsp"]


if __name__ == "__main__":
    unittest.main()
