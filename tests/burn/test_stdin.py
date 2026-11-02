"""Burn tests: reading stdin with `std.io` (MYLA-78) behaves the same in both
implementations, given the same bytes through a real pipe:

- the self-hosted interpreter (`selfhost/interp_main.my`),
- the self-hosted native backend (`selfhost/gen_main.my`).

(The Python interpreter and the Python native backend ran them too until they
were retired, MYLA-219; where a test has no expectation of its own, the
Python interpreter's output, recorded, is the expected one.)

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

from ._golden import golden
from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

# Python buffers a piped stdout unless PYTHONUNBUFFERED is set (as some CI
# environments do); the (retired Python) interpreter must not rely on it.
_ENV = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}


@golden("test_stdin.python_interpreter")
def _python_interpreter(path: str, data: str) -> tuple[str, int]:
    """(stdout, exit) of the Python interpreter running the program `path`
    with `data` (UTF-8) on stdin."""
    proc = subprocess.run([sys.executable, os.path.join(_REPO, "myla.py"), "run", path],
                          input=data.encode(), capture_output=True, timeout=60, env=_ENV)
    return proc.stdout.decode(), proc.returncode


# The two programs below were shared with the unit tests of the retired Python
# toolchain (`tests/unit/test_stdio.py`).

# Prints each line of stdin with its length, then the count.
LINES = """from std.io import stdin
fun main() {
    var r = stdin()
    var n = 0
    while true {
        match r.read_line() {
            Ok(Some(line)) => {
                n = n + 1
                print(format("{}: [{}] {}", n, line, len(line)))
            },
            Ok(None) => { break },
            Err(e) => {
                print("error")
                break
            },
        }
    }
    print(format("{} lines", n))
}
"""

# Reads messages framed by a Content-Length header, as the language server
# protocol does, through a struct that owns the reader.
FRAMED = """from std.io import stdin, Reader
from std.fs import IoError

struct Channel { input: Reader }

impl Channel {
    // The next message's body; None at the end of the input.
    fun next(var self) -> Result<Option<str>, IoError> {
        var length = -1
        while true {
            match self.input.read_line()? {
                Some(line) => {
                    if len(line) <= 1 { break }       // "" or "\\r"
                    length = digits_of(line)
                },
                None => { return Ok(None) },
            }
        }
        return self.input.read_exact(length)
    }
}

fun digits_of(s: str) -> int32 {
    var n = 0
    for c in chars(s) {
        if c >= '0' && c <= '9' { n = n * 10 + ((c as int32) - 48) }
    }
    return n
}

fun main() {
    var ch = Channel { input: stdin() }
    while true {
        match ch.next() {
            Ok(Some(body)) => { print(format("<{}>", body)) },
            Ok(None) => { break },
            Err(e) => {
                print("error")
                break
            },
        }
    }
}
"""

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

# Waits for input with a timeout (MYLA-80): nothing has been sent at first,
# then a line, then the end of the input.
WAIT = """from std.io import stdin, println
fun main() {
    var r = stdin()
    println(format("{}", r.ready(200)))
    println("go")
    println(format("{}", r.ready(20000)))
    match r.read_line() {
        Ok(Some(line)) => { println(line) },
        _ => { println("none") },
    }
    println(format("{}", r.ready(20000)))
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
        cls.paths: dict[str, str] = {}
        for name, source in [("lines", LINES), ("framed", FRAMED), ("echo", ECHO_ALL),
                             ("bad_fd", BAD_FD), ("ping", PING), ("wait", WAIT)]:
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
        asm = subprocess.run([cls.gen, path, STDLIB_ROOT], capture_output=True, text=True, check=True)
        sh_native = os.path.join(d, "sh_native")
        with open(sh_native + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm.stdout)
        subprocess.run(["as", "--64", "-o", sh_native + ".o", sh_native + ".s"], check=True)
        subprocess.run(["ld", "-o", sh_native, sh_native + ".o"], check=True)
        cls.paths[name] = path
        return {
            "self-hosted interpreter": [cls.interp, path, STDLIB_ROOT],
            "self-hosted native": [sh_native],
        }

    def outputs(self, name: str, data: bytes) -> dict[str, tuple[bytes, int]]:
        out = {}
        for impl, argv in self.programs[name].items():
            proc = subprocess.run(argv, input=data, capture_output=True, timeout=60, env=_ENV)
            out[impl] = (proc.stdout, proc.returncode)
        return out

    def python_interpreter(self, name: str, data: bytes) -> bytes:
        """The retired Python interpreter's output for the program `name`
        given `data` (recorded)."""
        out, code = _python_interpreter(self.paths[name], data.decode())
        self.assertEqual(code, 0)
        return out.encode()

    def assert_all(self, name: str, data: bytes, expected: bytes | None = None) -> None:
        results = self.outputs(name, data)
        reference = expected if expected is not None else self.python_interpreter(name, data)
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
        reference = self.python_interpreter("lines", data)
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

    def test_waiting_for_input(self) -> None:
        for impl, argv in self.programs["wait"].items():
            with self.subTest(implementation=impl):
                proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=_ENV)
                try:
                    self.assertEqual(_read_line(proc, 30), b"false\n")   # timed out
                    self.assertEqual(_read_line(proc, 30), b"go\n")
                    proc.stdin.write(b"hello\n")
                    proc.stdin.flush()
                    self.assertEqual(_read_line(proc, 30), b"true\n")
                    self.assertEqual(_read_line(proc, 30), b"hello\n")
                    proc.stdin.close()
                    self.assertEqual(_read_line(proc, 30), b"true\n")    # the end of the input
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
