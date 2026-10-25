"""End-to-end test of the language server's diagnostics over stdio JSON-RPC.

Needs the optional `lsp` extra (pygls); skipped without it.
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

    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(_REPO, "myla.py"), "lsp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self.next_id = 1
        self.messages: queue.Queue = queue.Queue()
        threading.Thread(target=self._read_all, daemon=True).start()

    def send(self, method, params, request=False):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if request:
            msg["id"] = self.next_id
            self.next_id += 1
        body = json.dumps(msg).encode()
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

    def diagnostics(self, count):
        """The next `count` publishDiagnostics notifications, as {uri: [message]}."""
        got = {}
        while len(got) < count:
            msg = self.receive()
            if msg.get("method") == "textDocument/publishDiagnostics":
                p = msg["params"]
                got[p["uri"]] = [d["message"] for d in p["diagnostics"]]
        return got

    def close(self):
        self.proc.kill()
        self.proc.wait()
        self.proc.stdin.close()
        self.proc.stdout.close()


def _uri(path):
    return "file://" + os.path.realpath(path)


@unittest.skipUnless(HAVE_PYGLS, "needs the lsp extra (pygls)")
class TestLspDiagnostics(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="myla_lsp_")
        self.main = os.path.join(self.root, "main.my")
        self.bad = os.path.join(self.root, "bad.my")
        self.main_src = "from .bad import f\nfun main() {\n    print(f())\n}\n"
        with open(self.main, "w") as fh:
            fh.write(self.main_src)
        with open(self.bad, "w") as fh:
            fh.write("pub fun f() -> int {\n    return \"oops\"\n}\n")
        self.client = _Client()
        self.addCleanup(self.client.close)
        self.client.send("initialize", {"processId": None, "rootUri": _uri(self.root),
                                        "capabilities": {}}, request=True)
        self.assertIn("result", self.client.receive())
        self.client.send("initialized", {})

    def open(self, path, text):
        self.client.send("textDocument/didOpen", {"textDocument": {
            "uri": _uri(path), "languageId": "myla", "version": 1, "text": text}})

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


if __name__ == "__main__":
    unittest.main()
