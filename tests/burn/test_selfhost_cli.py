"""Burn test: the self-hosted `myla` CLI ([[selfhost/main.my]], MYLA-31, MYLA-35).

The CLI is built by the Python backend into `<tmp>/build/myla`, next to a
`<tmp>/src/myla` that links to this repository's stdlib, the layout of a
checkout. It is run from another directory, so the stdlib root must come from
the binary's own location.
"""
from __future__ import annotations

import os
import shutil
import subprocess
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


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class SelfHostedCli(unittest.TestCase):
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
