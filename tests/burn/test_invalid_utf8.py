"""Burn test: strings that aren't valid UTF-8 (MYLA-12).

A `str` holds bytes. A file read with `read_to_string` or a string built with
`append_byte` can hold bytes that aren't UTF-8; `len`, indexing, `+`, `format`,
`==`, map keys and `print` work on the bytes, and `chars()` gives U+FFFD for
every byte that isn't part of a well-formed sequence.

The program runs four ways, each compared byte for byte (stdout may hold the
invalid bytes, so nothing is decoded) with the expected output: the Python
interpreter (`myla run`), the Python native backend, and the self-hosted
compiler and interpreter (built by the Python backend).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

from myla.compiler import build
from myla.loader import default_stdlib_root, link
from myla.types import check

from ._native import CAN_BUILD_NATIVE, SKIP_REASON

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_MYLA = os.path.join(_REPO, "myla.py")

# ASCII, two stray bytes, a truncated 4-byte sequence, an overlong NUL, an
# encoded surrogate, two valid scalars, and a sequence cut off by the end.
DATA = (b"ab\xff\xfecd" + b"\xf0\x9f\x98" + b"\xc0\x80" + b"\xed\xa0\x80"
        + "é".encode() + "😀".encode() + b"\xe2\x82")
FFFD = 0xFFFD
DATA_CHARS = ([0x61, 0x62, FFFD, FFFD, 0x63, 0x64] + [FFFD] * 3 + [FFFD] * 2 + [FFFD] * 3
              + [0xE9, 0x1F600] + [FFFD] * 2)

PROGRAM = """\
from std.fs import read_to_string

fun show(s: str) {
    print(len(s))
    var line = StringBuilder()
    var i = 0
    while i < len(s) {
        append(line, format("{} ", s[i]))
        i = i + 1
    }
    print(build(line))
    var cps = StringBuilder()
    for c in chars(s) {
        append(cps, format("{} ", c as uint32))
    }
    print(build(cps))
    print(s)
}

fun byte(b: uint8) -> str {
    var sb = StringBuilder()
    append_byte(sb, b)
    return build(sb)
}

fun main() {
    match read_to_string("bin.dat") {
        Ok(s) => {
            show(s)
            show(format("<{}>", s + "!"))
            // the two halves of an é, joined
            let joined = byte(0xC3u8) + byte(0xA9u8)
            print(joined == "é")
            print(format("{}{}", byte(0xC3u8), byte(0xA9u8)) == "é")
            let m = [joined: 1]
            print(contains(m, "é"))
            show(joined)
            print(byte(0xFFu8) == byte(0xFEu8))
        },
        Err(e) => print("cannot read bin.dat"),
    }
}
"""


def _show(data: bytes, chars: list[int]) -> bytes:
    return b"".join([
        f"{len(data)}\n".encode(),
        "".join(f"{b} " for b in data).encode() + b"\n",
        "".join(f"{c} " for c in chars).encode() + b"\n",
        data + b"\n",
    ])


EXPECTED = b"".join([
    _show(DATA, DATA_CHARS),
    _show(b"<" + DATA + b"!>", [0x3C] + DATA_CHARS + [0x21, 0x3E]),
    b"true\ntrue\ntrue\n",
    _show("é".encode(), [0xE9]),
    b"false\n",
])


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class InvalidUtf8(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = cls._tmp.name
        with open(os.path.join(cls.dir, "bin.dat"), "wb") as fh:
            fh.write(DATA)
        cls.prog = os.path.join(cls.dir, "main.my")
        with open(cls.prog, "w", encoding="utf-8") as fh:
            fh.write(PROGRAM)
        cls.stdlib = default_stdlib_root()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _run(self, argv: list[str]) -> bytes:
        proc = subprocess.run(argv, cwd=self.dir, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="replace"))
        return proc.stdout

    def _tool(self, name: str) -> str:
        """`selfhost/<name>.my` built by the Python backend."""
        binary = os.path.join(self.dir, name)
        if not os.path.exists(binary):
            tool = os.path.join(_REPO, "selfhost", f"{name}.my")
            build(check(link(tool, stdlib_root=self.stdlib)), binary)
        return binary

    def test_python_interpreter(self) -> None:
        self.assertEqual(self._run([sys.executable, _MYLA, "run", self.prog]), EXPECTED)

    def test_python_native_backend(self) -> None:
        binary = os.path.join(self.dir, "prog_py")
        build(check(link(self.prog, stdlib_root=self.stdlib)), binary)
        self.assertEqual(self._run([binary]), EXPECTED)

    def test_self_hosted_compiler(self) -> None:
        asm = self._run([self._tool("gen_main"), self.prog, self.stdlib])
        asm_path = os.path.join(self.dir, "prog_self.s")
        with open(asm_path, "wb") as fh:
            fh.write(asm)
        binary = os.path.join(self.dir, "prog_self")
        subprocess.run(["as", "--64", "-o", binary + ".o", asm_path], check=True)
        subprocess.run(["ld", "-o", binary, binary + ".o"], check=True)
        self.assertEqual(self._run([binary]), EXPECTED)

    def test_self_hosted_interpreter(self) -> None:
        self.assertEqual(self._run([self._tool("interp_main"), self.prog, self.stdlib]), EXPECTED)


if __name__ == "__main__":
    unittest.main()
