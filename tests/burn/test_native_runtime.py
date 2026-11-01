"""Burn test: the native runtime's robustness (MYLA-17), for the self-hosted
compiler (and for the Python backend until it was retired, MYLA-219).

- A runtime error writes `runtime error: <message>` to stderr (the
  interpreter's message, without the values), then the source position as
  `  --> file:line:col`, the interpreter's second line (MYLA-65, MYLA-66), and
  exits with status 1, instead of exiting silently. (The interpreter's
  positions are the retired Python interpreter's, recorded.)
- Output isn't lost when a `write` is short or can't proceed yet: here stdout
  is a non-blocking pipe whose reader starts late, so the pipe fills and
  `write` returns EAGAIN or writes part of the buffer.
"""
from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import tempfile
import time
import unittest

from ._golden import golden
from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_MYLA = os.path.join(_REPO, "myla.py")


@golden("test_native_runtime.interpreter_run")
def _interpreter_run(path: str) -> tuple[int, str]:
    """(exit, stderr) of the Python CLI's `myla run <file>`, run in the file's
    directory with its bare name, so the positions name it that way."""
    proc = subprocess.run([sys.executable, _MYLA, "run", os.path.basename(path)],
                          cwd=os.path.dirname(path), capture_output=True, text=True)
    return proc.returncode, proc.stderr

# (name, statements in main from line 4 on, the message, the position). The
# position is the interpreter's (checked against it below): the node that
# raises the error, an index's `[`, a call's `(`, a binary operator.
TRAPS = [
    ("list_index", "let xs = [1, 2]\n    print(xs[n + 3])", "index out of bounds", "5:13"),
    ("string_index", 'let s = "ab"\n    print(s[n + 1])', "index out of bounds", "5:12"),
    ("map_key", 'let m = ["a": 1]\n    print(m["b"])', "map key not found", "5:12"),
    ("assign_list_index", "var xs = [1, 2]\n    xs[n + 5] = 3", "index out of bounds", "5:7"),
    ("assign_inner_index", "var g = [[1]]\n    g[n][0] = 3", "index out of bounds", "5:6"),
    ("assign_outer_index", "var g = [[1]]\n    g[0][n] = 3", "index out of bounds", "5:9"),
    ("pop_empty", "var xs: [int] = []\n    print(pop(xs) + n)", "pop from an empty list", "5:14"),
    ("division", "print(7 / (n - 1))", "division by zero", "4:13"),
    ("modulo", "print(7 % (n - 1))", "modulo by zero", "4:13"),
    ("char_surrogate", "print((n + 55295) as char)", "invalid char", "4:23"),
    ("char_above_max", "print((n + 1114111) as char)", "invalid char", "4:25"),
    ("string_range", 'var sb = StringBuilder()\n    append(sb, "abc", n, 9)', "index out of bounds", "5:11"),
    ("panic", 'panic(f"boom {n}")', "boom 1", "4:10"),
    ("assert", "assert(n == 2)", "assertion failed", "4:11"),
    ("assert_message", 'assert(n == 2, "n is not 2")', "n is not 2", "4:11"),
    ("unreachable", "unreachable()", "reached unreachable code", "4:16"),
]

# A runtime error in an imported module names that module's file: in a
# function, a method and a lambda.
MODULE_MAIN = """\
from .lib import Box, at, apply
fun main() {
    let b = Box { xs: [1, 2] }
    let which = len(b.xs)
    print(which)
    if which == WHICH { print(at(b.xs, 7)) }
    if which == WHICH { print(b.get(9)) }
    if which == WHICH { print(apply(2)) }
}
"""
MODULE_LIB = """\
pub struct Box { xs: [int] }
impl Box {
    fun get(self, i: int) -> int {
        return self.xs[i]
    }
}
pub fun at(xs: [int], i: int) -> int {
    return xs[i]
}
pub fun apply(k: int) -> int {
    let f = (d: int) => 10 / (d - 2)
    return f(k)
}
"""
MODULE_TRAPS = [   # (line of main.my to keep, message, position)
    (6, "index out of bounds", "lib.my:8:14"),
    (7, "index out of bounds", "lib.my:4:23"),
    (8, "division by zero", "lib.my:11:28"),
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
        cls.stdlib = STDLIB_ROOT
        cls.gen = selfhost_tool("gen_main")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def write(self, name: str, source: str, directory: str | None = None) -> str:
        path = os.path.join(directory or self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)
        return path

    def binaries(self, name: str, source: str, cwd: str | None = None) -> list[tuple[str, str]]:
        """`source` built by the self-hosted compiler as `<name>.my` in `cwd`,
        compiled from there with that relative path as `myla build` would be
        (so the positions name `<name>.my`): [(backend, binary)]."""
        cwd = cwd or self.dir
        self.write(name + ".my", source, cwd)
        asm = subprocess.run([self.gen, name + ".my", self.stdlib], cwd=cwd,
                             capture_output=True, text=True, check=True).stdout
        sh = os.path.join(cwd, name + "_self")
        self.write(name + "_self.s", asm, cwd)
        subprocess.run(["as", "--64", "-o", sh + ".o", sh + ".s"], check=True)
        subprocess.run(["ld", "-o", sh, sh + ".o"], check=True)
        return [("self-hosted", sh)]

    def interpreter_position(self, name: str, cwd: str | None = None) -> str:
        """The `  --> file:line:col` line `myla run` prints for `<name>.my`
        (the retired Python interpreter's, recorded)."""
        code, stderr = _interpreter_run(os.path.join(cwd or self.dir, name + ".my"))
        self.assertEqual(code, 1, stderr)
        return stderr.splitlines()[1]

    def test_runtime_errors_have_messages_and_positions(self):
        for name, body, message, position in TRAPS:
            source = f"fun main() {{\n    let n = 1\n    print(n)\n    {body}\n    print(99)\n}}\n"
            for backend, binary in self.binaries(name, source):
                with self.subTest(trap=name, backend=backend):
                    proc = subprocess.run([binary], capture_output=True, text=True)
                    where = f"  --> {name}.my:{position}"
                    self.assertEqual((proc.stdout, proc.stderr, proc.returncode),
                                     ("1\n", f"runtime error: {message}\n{where}\n", 1))
                    self.assertEqual(where, self.interpreter_position(name))

    def test_a_stack_overflow_is_reported(self):
        # the main stack grows to 120 MiB, and running out of it is a runtime
        # error, as from the interpreters (MYLA-182)
        source = ("fun down(n: int) -> int {\n    if n == 0 {\n        return 0\n    }\n"
                  "    return down(n - 1) + 1\n}\n\n"
                  "fun main() {\n    print(down(1000000))\n    print(down(100000000))\n}\n")
        for backend, binary in self.binaries("overflow", source):
            with self.subTest(backend=backend):
                proc = subprocess.run([binary], capture_output=True, text=True, timeout=60)
                # a million calls fit in 120 MiB, where 8 MiB held some 130,000
                self.assertEqual((proc.stdout, proc.stderr, proc.returncode),
                                 ("1000000\n", "runtime error: stack overflow\n", 1))

    def test_runtime_errors_in_an_imported_module_name_its_file(self):
        for line, message, position in MODULE_TRAPS:
            with self.subTest(line=line):
                project = tempfile.mkdtemp(dir=self.dir)
                self.write("lib.my", MODULE_LIB, project)
                lines = MODULE_MAIN.splitlines(keepends=True)
                lines = [l.replace("WHICH", "2" if i + 1 == line else "0") for i, l in enumerate(lines)]
                source = "".join(lines)
                where = f"  --> {position}"
                self.write("main.my", source, project)
                self.assertEqual(self.interpreter_position("main", project), where)
                for backend, binary in self.binaries("main", source, project):
                    with self.subTest(backend=backend):
                        proc = subprocess.run([binary], capture_output=True, text=True)
                        self.assertEqual((proc.stdout, proc.stderr, proc.returncode),
                                         ("2\n", f"runtime error: {message}\n{where}\n", 1))

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
