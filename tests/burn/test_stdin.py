"""Burn tests: reading stdin with `std.io` (MYLA-78) behaves the same in all
four implementations, given the same bytes through a real pipe:

- the Python interpreter (`myla.py run`),
- the Python native backend,
- the self-hosted interpreter (`selfhost/interp_main.my`),
- the self-hosted native backend (`selfhost/gen_main.my`).

The programs read lines, Content-Length framed messages (as the language
server protocol does), everything at once (binary bytes, echoed back), and
from a bad descriptor. An interactive exchange checks that what a program
writes is out before it waits for input, which a request/response protocol
needs.
"""
from __future__ import annotations

import os
import select
import subprocess
import sys
import tempfile
import unittest

from myla.compiler import build
from myla.loader import default_stdlib_root

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, check_file
from ._tools import selfhost_tool
from tests.unit.test_stdio import FRAMED, LINES

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

# Python buffers a piped stdout unless PYTHONUNBUFFERED is set (as some CI
# environments do); the interpreter must not rely on it.
_ENV = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}

ECHO_ALL = """from std.io import stdin, write
fun main() {
    var r = stdin()
    match r.read_to_end() {
        Ok(s) => {
            print(len(s))
            write(1, s)
        },
        Err(e) => { print("error") },
    }
}
"""

BAD_FD = """from std.io import reader
from std.fs import IoError
fun main() {
    var r = reader(99)
    match r.read_line() {
        Err(IoError.Other(code)) => { print(code) },
        _ => { print("no error") },
    }
    match r.read_to_end() {
        Err(IoError.Other(code)) => { print(code) },
        _ => { print("no error") },
    }
}
"""

# Answers each line at once, so the driver can wait for the answer before it
# sends the next one.
PING = """from std.io import stdin, println
fun main() {
    var r = stdin()
    while true {
        match r.read_line() {
            Ok(Some(line)) => { println(format("got {}", line)) },
            _ => { break },
        }
    }
    println("bye")
}
"""


def _big_input() -> bytes:
    """About 100 KB of lines of varying length, with multi-byte characters
    that fall across the reader's chunk boundaries."""
    lines = []
    for i in range(1500):
        lines.append(("ab λ" * (i % 37) + f"{i}😀").encode())
    return b"\n".join(lines) + b"\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class StdinParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.interp = selfhost_tool("interp_main")
        cls.gen = selfhost_tool("gen_main")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.programs: dict[str, dict[str, list[str]]] = {}
        for name, source in [("lines", LINES), ("framed", FRAMED), ("echo", ECHO_ALL),
                             ("bad_fd", BAD_FD), ("ping", PING)]:
            cls.programs[name] = cls._commands(name, source)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    @classmethod
    def _commands(cls, name: str, source: str) -> dict[str, list[str]]:
        """The command that runs `source` in each implementation."""
        d = os.path.join(cls.tmp.name, name)
        os.makedirs(d)
        path = os.path.join(d, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)
        py_native = os.path.join(d, "py_native")
        build(check_file(path), py_native)
        asm = subprocess.run([cls.gen, path, default_stdlib_root()], capture_output=True, text=True, check=True)
        sh_native = os.path.join(d, "sh_native")
        with open(sh_native + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm.stdout)
        subprocess.run(["as", "--64", "-o", sh_native + ".o", sh_native + ".s"], check=True)
        subprocess.run(["ld", "-o", sh_native, sh_native + ".o"], check=True)
        return {
            "python interpreter": [sys.executable, os.path.join(_REPO, "myla.py"), "run", path],
            "python native": [py_native],
            "self-hosted interpreter": [cls.interp, path, default_stdlib_root()],
            "self-hosted native": [sh_native],
        }

    def outputs(self, name: str, data: bytes) -> dict[str, tuple[bytes, int]]:
        out = {}
        for impl, argv in self.programs[name].items():
            proc = subprocess.run(argv, input=data, capture_output=True, timeout=60, env=_ENV)
            out[impl] = (proc.stdout, proc.returncode)
        return out

    def assert_all(self, name: str, data: bytes, expected: bytes | None = None) -> None:
        results = self.outputs(name, data)
        reference = expected if expected is not None else results["python interpreter"][0]
        for impl, (stdout, code) in results.items():
            with self.subTest(implementation=impl):
                self.assertEqual(code, 0)
                self.assertEqual(stdout, reference)

    def test_lines(self) -> None:
        self.assert_all("lines", b"one\ntwo\r\n\n\xce\xbb \xc3\xb6\nlast",
                        "1: [one] 3\n2: [two\r] 4\n3: [] 0\n4: [λ ö] 5\n5: [last] 4\n5 lines\n".encode())

    def test_no_input(self) -> None:
        self.assert_all("lines", b"", b"0 lines\n")

    def test_many_lines_across_chunks(self) -> None:
        data = _big_input()
        results = self.outputs("lines", data)
        reference = results["python interpreter"][0]
        self.assertTrue(reference.endswith(b"1500 lines\n"))
        last = ("1500: [" + "ab λ" * (1499 % 37) + "1499😀]").encode()
        self.assertTrue(last in reference, "the last line is missing or wrong")
        for impl, (stdout, code) in results.items():
            with self.subTest(implementation=impl):
                self.assertEqual((stdout, code), (reference, 0))

    def test_framed_messages(self) -> None:
        body = '{"jsonrpc":"2.0","method":"λ"}'.encode()
        data = (b"Content-Length: 5\r\n\r\nhello"
                + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
                + b"Content-Length: 99\r\n\r\ncut short")
        self.assert_all("framed", data, b"<hello>\n<" + body + b">\n")

    def test_binary_input_is_kept_exactly(self) -> None:
        data = bytes(range(256)) * 40 + b"\xff\xfe tail"
        self.assert_all("echo", data, str(len(data)).encode() + b"\n" + data)

    def test_errors(self) -> None:
        self.assert_all("bad_fd", b"", b"9\n9\n")

    def test_output_is_out_before_reading(self) -> None:
        for impl, argv in self.programs["ping"].items():
            with self.subTest(implementation=impl):
                proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=_ENV)
                try:
                    for word in ("first", "second", "λ"):
                        proc.stdin.write(word.encode() + b"\n")
                        proc.stdin.flush()
                        self.assertEqual(_read_line(proc, 30), f"got {word}\n".encode())
                    proc.stdin.close()
                    self.assertEqual(_read_line(proc, 30), b"bye\n")
                    self.assertEqual(proc.wait(30), 0)
                finally:
                    proc.kill()
                    proc.wait()
                    proc.stdout.close()


def _read_line(proc: subprocess.Popen, timeout: float) -> bytes:
    """One line of the process's output, or what arrived before `timeout`."""
    fd = proc.stdout.fileno()
    line = b""
    while not line.endswith(b"\n"):
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            break
        byte = os.read(fd, 1)
        if not byte:
            break
        line += byte
    return line


if __name__ == "__main__":
    unittest.main()
