"""Burn test: the native runtime's robustness (MYLA-17), for the Python
backend and the self-hosted compiler.

- A runtime error writes `runtime error: <message>` to stderr (the
  interpreter's message, without the values) and exits with status 1, instead
  of exiting silently.
- Output isn't lost when a `write` is short or can't proceed yet: here stdout
  is a non-blocking pipe whose reader starts late, so the pipe fills and
  `write` returns EAGAIN or writes part of the buffer.
"""
from __future__ import annotations

import fcntl
import os
import subprocess
import tempfile
import time
import unittest

from myla.compiler import build
from myla.loader import default_stdlib_root, link
from myla.types import check

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

# (name, statements in main, the message)
TRAPS = [
    ("list_index", "let xs = [1, 2]\n    print(xs[n + 3])", "index out of bounds"),
    ("string_index", 'let s = "ab"\n    print(s[n + 1])', "index out of bounds"),
    ("map_key", 'let m = ["a": 1]\n    print(m["b"])', "map key not found"),
    ("assign_list_index", "var xs = [1, 2]\n    xs[n + 5] = 3", "index out of bounds"),
    ("pop_empty", "var xs: [int] = []\n    print(pop(xs) + n)", "pop from an empty list"),
    ("division", "print(7 / (n - 1))", "division by zero"),
    ("modulo", "print(7 % (n - 1))", "modulo by zero"),
]

LINES = 20000
WRITER = f"""\
fun main() {{
    var i = 0
    while i < {LINES} {{
        print("0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789")
        i = i + 1
    }}
}}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class NativeRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = cls._tmp.name
        cls.stdlib = default_stdlib_root()
        cls.gen = selfhost_tool("gen_main")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def binaries(self, name: str, source: str) -> list[tuple[str, str]]:
        """`source` built by both backends: [(backend, binary)]."""
        src = os.path.join(self.dir, name + ".my")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(source)
        py = os.path.join(self.dir, name + "_py")
        build(check(link(src, stdlib_root=self.stdlib)), py)
        asm = subprocess.run([self.gen, src, self.stdlib], capture_output=True, text=True, check=True).stdout
        sh = os.path.join(self.dir, name + "_self")
        with open(sh + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm)
        subprocess.run(["as", "--64", "-o", sh + ".o", sh + ".s"], check=True)
        subprocess.run(["ld", "-o", sh, sh + ".o"], check=True)
        return [("python", py), ("self-hosted", sh)]

    def test_runtime_errors_have_messages(self):
        for name, body, message in TRAPS:
            source = f"fun main() {{\n    let n = 1\n    print(n)\n    {body}\n    print(99)\n}}\n"
            for backend, binary in self.binaries(name, source):
                with self.subTest(trap=name, backend=backend):
                    proc = subprocess.run([binary], capture_output=True, text=True)
                    self.assertEqual((proc.stdout, proc.stderr, proc.returncode),
                                     ("1\n", f"runtime error: {message}\n", 1))

    def test_no_output_is_lost_on_a_non_blocking_pipe(self):
        expected = LINES * 101
        for backend, binary in self.binaries("writer", WRITER):
            with self.subTest(backend=backend):
                r, w = os.pipe()
                fcntl.fcntl(w, fcntl.F_SETFL, fcntl.fcntl(w, fcntl.F_GETFL) | os.O_NONBLOCK)
                proc = subprocess.Popen([binary], stdout=w)
                os.close(w)
                time.sleep(0.3)                 # let the pipe fill up
                got = 0
                with os.fdopen(r, "rb") as reader:
                    while chunk := reader.read(65536):
                        got += len(chunk)
                self.assertEqual(proc.wait(), 0)
                self.assertEqual(got, expected)


if __name__ == "__main__":
    unittest.main()
