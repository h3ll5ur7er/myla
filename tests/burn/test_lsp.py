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
from tests.integration.test_lsp_diagnostics import LspScenarios, _uri


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
        cls.tmp = tempfile.TemporaryDirectory()
        asm = subprocess.run([selfhost_tool("gen_main"), os.path.join(_REPO, "tools", "lsp", "main.my"),
                              default_stdlib_root()], capture_output=True, text=True, check=True)
        cls.binary = os.path.join(cls.tmp.name, "myla-lsp")
        with open(cls.binary + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm.stdout)
        subprocess.run(["as", "--64", "-o", cls.binary + ".o", cls.binary + ".s"], check=True)
        subprocess.run(["ld", "-o", cls.binary, cls.binary + ".o"], check=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
