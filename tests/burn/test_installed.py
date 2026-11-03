"""Burn test: an installed toolchain carries its standard library (MYLA-243).

Only the binaries are installed, in a prefix of their own, and found through
a symbolic link on the PATH, the way the owner installed `myla` into
/usr/bin: no repository, no `lib/`, no `--stdlib`. `myla new`, `run`, `test`,
`build` and `build -g` work there, with the standard library the binary
carries; `MYLA_STDLIB` and `--stdlib` replace it with a directory. The
language server finds the standard library too: hover and completion know
`std.io`, and a definition in it opens as a `myla-std:` document whose text
the server gives (`myla/stdSource`)."""
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.burn._lsp_scenarios import _Client, _uri
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, myla_tool, selfhost_tool

_MAIN = """from std.io import println
from std.json import parse, to_string
from std.process import env

// The greeting `main` prints.
#test("hi")["Hello from hi!"]
fun greeting(name: str) -> str {
    return f"Hello from {name}!"
}

fun main() {
    println(greeting("hi"))
    match parse("[1, 2]") {
        Ok(j) => println(to_string(j)),
        Err(e) => println("bad json"),
    }
    match env("HOME_OF_TEST") {
        Some(v) => println(v),
        None => println("unset"),
    }
}
"""

_WANT = "Hello from hi!\n[1,2]\nunset\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Installed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp(prefix="myla_installed_")
        # the binaries in a prefix of their own, linked into a bin/ on the PATH
        opt = os.path.join(cls.tmp, "opt", "myla")
        os.makedirs(opt)
        shutil.copy(selfhost_tool("main"), os.path.join(opt, "myla"))
        shutil.copy(myla_tool("tools/lsp/main.my", "lsp"), os.path.join(opt, "myla-lsp"))
        cls.bin = os.path.join(cls.tmp, "bin")
        os.makedirs(cls.bin)
        for name in ("myla", "myla-lsp"):
            os.symlink(os.path.join(opt, name), os.path.join(cls.bin, name))
        cls.work = os.path.join(cls.tmp, "work")
        os.makedirs(cls.work)
        cls.env = {k: v for k, v in os.environ.items() if k not in ("MYLA_STDLIB", "HOME_OF_TEST")}
        cls.env["PATH"] = cls.bin + os.pathsep + "/usr/bin" + os.pathsep + "/bin"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, True)

    def myla(self, *argv, cwd=None, env=None):
        return subprocess.run(["myla", *argv], cwd=cwd or self.work, env=env or self.env, capture_output=True,
                              text=True)

    def project(self, name):
        made = self.myla("new", name)
        self.assertEqual(made.returncode, 0, made.stderr)
        root = os.path.join(self.work, name)
        with open(os.path.join(root, "src", "main.my"), "w", encoding="utf-8") as fh:
            fh.write(_MAIN)
        return root

    def test_a_project_runs_tests_and_builds(self):
        root = self.project("hi")
        ran = self.myla("run", cwd=root)
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (_WANT, "", 0))
        tested = self.myla("test", cwd=root)
        self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
        self.assertIn("PASS  greeting #1", tested.stdout)
        built = self.myla("build", cwd=root)
        self.assertEqual(built.returncode, 0, built.stderr)
        exe = subprocess.run([os.path.join(root, "build", "hi")], capture_output=True, text=True, env=self.env)
        self.assertEqual((exe.stdout, exe.returncode), (_WANT, 0))

    def test_a_debug_build_carries_the_pretty_printers(self):
        root = self.project("dbg")
        path = os.path.join(root, "src", "main.my")
        exe = os.path.join(self.work, "dbg_g")
        built = self.myla("build", "-g", path, "-o", exe)
        self.assertEqual(built.returncode, 0, built.stderr)
        with open(exe, "rb") as fh:
            data = fh.read()
        # the section's script name and a printer of lib/debug/myla_gdb.py
        self.assertTrue(b"myla-printers" in data and b"class StringPrinter" in data, "no pretty-printers")

    def test_an_error_in_the_standard_library_names_its_embedded_file(self):
        path = os.path.join(self.work, "bad_call.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("from std.io import println\nfun main() {\n    println(1)\n}\n")
        checked = self.myla("check", path)
        self.assertEqual(checked.returncode, 1)
        self.assertIn("bad_call.my:3:", checked.stderr)
        # a module of the embedded library that doesn't exist
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("from std.nope import x\nfun main() {}\n")
        checked = self.myla("check", path)
        self.assertEqual(checked.returncode, 1)
        self.assertIn("cannot resolve import 'std.nope'", checked.stderr)

    def test_a_directory_replaces_the_embedded_library(self):
        lib = os.path.join(self.tmp, "mylib")
        shutil.copytree(STDLIB_ROOT, lib)
        io = os.path.join(lib, "std", "io.my")
        with open(io, encoding="utf-8") as fh:
            text = fh.read()
        with open(io, "w", encoding="utf-8") as fh:
            fh.write(text.replace("pub fun println(s: str) {", "pub fun println(s: str) {\n    write(1, \"> \")", 1))
        path = os.path.join(self.work, "hello.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("from std.io import println\nfun main() {\n    println(\"x\")\n}\n")
        self.assertEqual(self.myla("run", path).stdout, "x\n")
        self.assertEqual(self.myla("run", path, "--stdlib", lib).stdout, "> x\n")
        env = dict(self.env, MYLA_STDLIB=lib)
        self.assertEqual(self.myla("run", path, env=env).stdout, "> x\n")
        self.assertEqual(self.myla("run", path, env=dict(self.env, MYLA_STDLIB="")).stdout, "x\n")

    def test_the_language_server_knows_the_standard_library(self):
        client = _Client([os.path.join(self.bin, "myla-lsp")])
        self.addCleanup(client.close)
        rid = client.send("initialize", {"processId": None, "rootUri": _uri(self.work), "capabilities": {}},
                          request=True)
        client.response(rid)
        client.send("initialized", {})
        path = os.path.join(self.work, "lsp_doc.my")
        text = "from std.io import println\nfun main() {\n    println(\"x\")\n}\n"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        uri = _uri(path)
        client.send("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "myla", "version": 1,
                                                              "text": text}})
        self.assertEqual(client.diagnostics(1)[uri], [])

        def request(method, params):
            reply = client.response(client.send(method, params, request=True))
            self.assertNotIn("error", reply)
            return reply["result"]

        at = {"textDocument": {"uri": uri}, "position": {"line": 2, "character": 6}}
        hover = request("textDocument/hover", at)
        self.assertIn("println", hover["contents"]["value"])
        found = request("textDocument/definition", at)
        self.assertEqual(found["uri"], "myla-std:/std/io.my")
        source = request("myla/stdSource", {"uri": found["uri"]})
        with open(os.path.join(STDLIB_ROOT, "std", "io.my"), encoding="utf-8") as fh:
            self.assertEqual(source["text"], fh.read())
        line = source["text"].split("\n")[found["range"]["start"]["line"]]
        self.assertIn("fun println", line)
        self.assertIsNone(request("myla/stdSource", {"uri": "myla-std:/std/nope.my"}))
        # completion in imports, from the embedded library
        for text, character, want in [("from std.\n", 9, {"io", "json", "fs"}),
                                      ("from std.io import \n", 19, {"println", "stdin"})]:
            client.send("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2},
                                                   "contentChanges": [{"text": text + "fun main() {}\n"}]})
            got = request("textDocument/completion", {"textDocument": {"uri": uri},
                                                      "position": {"line": 0, "character": character}})
            self.assertLessEqual(want, {i["label"] for i in got["items"]}, text)


if __name__ == "__main__":
    unittest.main()
