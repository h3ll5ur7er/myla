"""Burn test: the self-hosted `myla` CLI ([[selfhost/main.my]], MYLA-31, MYLA-35).

The CLI is built by the Python backend into `<tmp>/build/myla`, next to a
`<tmp>/src/myla` that links to this repository's stdlib, the layout of a
checkout. It is run from another directory, so the stdlib root must come from
the binary's own location.
"""
from __future__ import annotations

import os
import shutil
import glob
import subprocess
import sys
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

PROGRAM = """\
from std.process import args

#test(2)[4]
fun double(x: int) -> int {
    return x * 2
}

fun main() {
    let argv = args()
    print(len(argv))
    for a in argv {
        print(a)
    }
    print(double(21))
}
"""


class _Layout(unittest.TestCase):
    """The CLI in a checkout's layout, run from a work directory (no tests)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        root = cls._tmp.name
        os.makedirs(os.path.join(root, "build"))
        os.makedirs(os.path.join(root, "src"))
        os.symlink(os.path.join(_REPO, "src", "myla"), os.path.join(root, "src", "myla"))
        cls.myla = os.path.join(root, "build", "myla")
        shutil.copy(selfhost_tool("main"), cls.myla)
        cls.work = os.path.join(root, "work")       # the directory commands run in
        os.makedirs(cls.work)
        with open(os.path.join(cls.work, "prog.my"), "w", encoding="utf-8") as fh:
            fh.write(PROGRAM)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def myla_cmd(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.myla, *argv], cwd=self.work, capture_output=True, text=True)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class SelfHostedCli(_Layout):
    def test_run_finds_the_stdlib_and_passes_arguments(self):
        proc = self.myla_cmd("run", "prog.my", "a", "b c")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode),
                         ("3\nprog.my\na\nb c\n42\n", "", 0))

    def test_explicit_stdlib(self):
        proc = self.myla_cmd("run", "prog.my", "--stdlib", os.path.join(_REPO, "src", "myla"), "x")
        self.assertEqual(proc.stdout, "2\nprog.my\nx\n42\n")
        proc = self.myla_cmd("run", "prog.my", "--stdlib", "/nowhere")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("cannot resolve import 'std.process'", proc.stderr)

    def test_test(self):
        proc = self.myla_cmd("test", "prog.my")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("1/1 passed", proc.stdout)

    def test_build_leaves_only_the_binary(self):
        out = os.path.join(self.work, "out", "prog")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        proc = self.myla_cmd("build", "prog.my", "-o", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(os.listdir(os.path.dirname(out)), ["prog"])
        run = subprocess.run([out, "z"], capture_output=True, text=True)
        self.assertEqual(run.stdout, f"2\n{out}\nz\n42\n")


if __name__ == "__main__":
    unittest.main()


FAILING = """\
from std.process import exit
struct P { x: int, name: str }
enum E { A, B(int, str) }
#test()['b']
fun ch() -> char { return 'a' }
#test()[true]
fun b() -> bool { return false }
#test()["it's \\"q\\"\\n\\t\\\\ é😀"]
fun s() -> str { return "say \\"hi\\"" }
#test()["it's"]
fun s2() -> str { return "x'y" }
#test()[[1.5, 1.0e16, 1.0e-5, -0.0, 3.0]]
fun f() -> [float64] { return [0.1 + 0.2] }
#test()[0.5f32]
fun f32() -> float32 { return 0.1f32 }
#test()[P { x: 1, name: "a" }]
fun p() -> P { return P { x: 2, name: "b'" } }
#test()[E.B(1, "z")]
fun e() -> E { return E.A }
#test()[[1, 2]]
fun l() -> [int] { return [3] }
#test()[["a": [1]]]
fun m() -> [str: [int]] { var e: [str: [int]] = [:]
    return e }
#test()[["k": 1, "j": 2]]
fun m2() -> [str: int] { return ["j": 2, "k": 1] }
#test()[(1, 'c', "d")]
fun t() -> (int, char, str) { return (2, 'x', "y") }
#test([1, 2], 5)[0]
fun idx(xs: [int], i: int) -> int { return xs[i] }
#test()[Some(1)]
fun o() -> Option<int> { return None }
#test()[1u8]
fun u() -> uint8 { return 255u8 }
#test()[1]
fun pan() -> int { panic("boom")
    return 1 }
#test()[2]
fun quits() -> int { exit(3)
    return 2 }
#test()[3]
fun noisy() -> int { print("from a test")
    return 4 }
#test()[7]
fun after() -> int { return 7 }
"""


def _sources_with_tests() -> list[str]:
    files = (glob.glob(os.path.join(_REPO, "examples", "*.my")) + glob.glob(os.path.join(_REPO, "selfhost", "*.my"))
             + glob.glob(os.path.join(_REPO, "tools", "*", "*.my"))
             + glob.glob(os.path.join(_REPO, "src", "myla", "std", "*.my")))
    out = []
    for f in sorted(files):
        with open(f, encoding="utf-8") as fh:
            if "#test" in fh.read():
                out.append(f)
    return out


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestCommandParity(_Layout):
    """`myla test` of the self-hosted CLI prints what the Python one prints,
    with the same exit status (MYLA-81): on every source with `#test`s, and
    on failures of every kind (values shown as the Python interpreter's repr,
    runtime errors, `exit`, output from the tests)."""

    def both(self, path: str) -> tuple:
        py = subprocess.run([sys.executable, os.path.join(_REPO, "myla.py"), "test", path], cwd=self.work,
                            capture_output=True, text=True)
        # the Python CLI's stdlib root, not the layout's symlink to it: module
        # ids come from paths as written, and a stdlib module tested through
        # another root would be named as a project module
        my = self.myla_cmd("test", path, "--stdlib", os.path.join(_REPO, "src", "myla"))
        return (py.stdout, py.returncode), (my.stdout, my.returncode)

    def test_failures(self):
        path = os.path.join(self.work, "failing.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(FAILING)
        py, my = self.both(path)
        self.assertEqual(py[1], 1, py)
        self.assertIn("FAIL  quits #1: exited with status 3", py[0])
        self.assertEqual(my, py)

    def test_the_corpus(self):
        files = _sources_with_tests()
        self.assertGreater(len(files), 40)
        for path in files:
            with self.subTest(file=os.path.relpath(path, _REPO)):
                py, my = self.both(path)
                self.assertEqual(py[1], 0, py[0][-300:])
                self.assertEqual(my, py)


SESSION = """\
let x = 1 + 2
x
fun twice(n: int) -> int {
    return n * 2
}
twice(x)
struct P { x: int, name: str }
var p = P { x: twice(5), name: "é\\"q" }
p
p.x = 7
p.x
[1, 2]
["a": [1]]
(1, 'c', true)
Some(1.5)
let x = "now a string"
x
print(x)
y + 1
let xs = [1]
xs[3]
xs
for i in 0..3 {
    print(i)
}
from std.num import format_float
format_float(0.5)
twice("no")
"""

SESSION_OUT = """\
3
6
P { x: 10, name: "é\\"q" }
7
[1, 2]
["a": [1]]
(1, 'c', true)
Some(1.5)
"now a string"
now a string
[1]
0
1
2
"0.5"
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestRepl(_Layout):
    """`myla repl` (MYLA-82): lines in, values out; declarations accumulate,
    an open bracket continues the input, errors don't end the session."""

    def repl(self, text: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.myla, "repl"], cwd=self.work, input=text, capture_output=True, text=True,
                              timeout=120)

    def test_a_session(self):
        proc = self.repl(SESSION)
        self.assertEqual(proc.stdout, SESSION_OUT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # errors name the input's own line, and the session goes on
        self.assertIn("unknown name 'y'", proc.stderr)
        self.assertIn("runtime error: list index 3 out of bounds (len 1)", proc.stderr)
        self.assertIn("  --> <input>:1:", proc.stderr)
        self.assertEqual(proc.stderr.count("error"), 3, proc.stderr)
        # the carets underline the offending range (MYLA-65)
        self.assertIn('1 | twice("no")\n  |       ^^^^\n', proc.stderr)

    def test_errors_inside_a_multiline_input(self):
        proc = self.repl("fun f() -> int {\n    let a = 1\n    return b\n}\nf()\n1\n")
        self.assertEqual(proc.stdout, "1\n")
        self.assertIn("  --> <input>:3:", proc.stderr)
        self.assertIn("3 |     return b", proc.stderr)
        proc = self.repl("1\nfun g() -> int {\n    let a = 1\n}\n")
        self.assertIn("1 | fun g() -> int {\n  | ^^^^^^^^^^^^^^^^\n", proc.stderr)

    def test_exit_ends_the_session(self):
        proc = self.repl("from std.process import exit\nprint(1)\nexit(4)\nprint(2)\n")
        self.assertEqual((proc.stdout, proc.returncode), ("1\n", 4))

