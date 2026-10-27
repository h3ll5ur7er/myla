"""Burn test: the project commands of the self-hosted `myla` (MYLA-94, D73).

`myla new`, `build`, `run`, `test`, `check` and `clean` run in project mode when
no `.my` file is given: they find `myla.toml` from the working directory
upwards and build `src/main.my` with the packages the project model
([[selfhost/project.my]], MYLA-93) works out, passed to the loader as
`--package` pairs (MYLA-92). The CLI runs in a checkout's layout, as in
test_selfhost_cli.py, so the standard library comes from the binary's location.
"""
from __future__ import annotations

import os
import subprocess
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from .test_selfhost_cli import _Layout

GEO_MANIFEST = """\
[package]
name = "geo"
version = "1.2.0"
"""

GEO_LIB = """\
pub import .shapes as shapes

// The area of a w by h rectangle.
#test(2, 3)[6]
pub fun area(w: int, h: int) -> int {
    return w * h
}
"""

GEO_SHAPES = """\
pub struct Square { side: int }

#test(Square { side: 3 })[12]
pub fun perimeter(s: Square) -> int {
    return 4 * s.side
}
"""

APP_MANIFEST = """\
[package]
name = "app"
version = "0.1.0"

[dependencies]
geo = { path = "../geo" }
"""

APP_MAIN = """\
from std.process import args
import geo
from geo.shapes import Square, perimeter
import util.strings as strings

#test(1)[2]
fun twice(n: int) -> int {
    return 2 * n
}

fun main() {
    print(geo.area(2, twice(3)))
    print(perimeter(Square { side: 5 }))
    print(strings.shout("hi"))
    for a in args() {
        print(a)
    }
}
"""

APP_STRINGS = """\
#test("a")["a!"]
#test("b")["b?"]
pub fun shout(s: str) -> str {
    return s + "!"
}
"""


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestNewProject(_Layout):
    """`myla new` and the commands on the project it creates."""

    def run_in(self, cwd: str, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.myla, *argv], cwd=cwd, capture_output=True, text=True)

    def test_new_build_run_test_check_clean(self):
        proc = self.myla_cmd("new", "hello")
        self.assertEqual((proc.stderr, proc.returncode), ("", 0))
        self.assertEqual(proc.stdout, "created package 'hello' in hello/\n")
        root = os.path.join(self.work, "hello")
        with open(os.path.join(root, "myla.toml"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), '[package]\nname = "hello"\nversion = "0.1.0"\n\n[dependencies]\n')
        with open(os.path.join(root, ".gitignore"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "build/\n.myla/\n")
        self.assertTrue(os.path.isfile(os.path.join(root, "src", "main.my")))

        proc = self.run_in(root, "run")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("Hello from hello!\n", "", 0))
        proc = self.run_in(root, "test")
        self.assertEqual((proc.stderr, proc.returncode), ("", 0))
        self.assertEqual(proc.stdout, "== src/main.my\nPASS  greeting #1\n\n1/1 passed in 1 file.\n")
        proc = self.run_in(root, "check")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("", "", 0))

        proc = self.run_in(root, "build")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("", "", 0))
        binary = os.path.join(root, "build", "hello")
        self.assertEqual(os.listdir(os.path.join(root, "build")), ["hello"])
        run = subprocess.run([binary], capture_output=True, text=True)
        self.assertEqual(run.stdout, "Hello from hello!\n")

        proc = self.run_in(root, "clean")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("", "", 0))
        self.assertFalse(os.path.exists(os.path.join(root, "build")))
        proc = self.run_in(root, "clean")          # nothing to remove is fine
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_new_errors(self):
        proc = self.myla_cmd("new", "1abc")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("'1abc' is not a valid package name", proc.stderr)
        proc = self.myla_cmd("new", "fun")
        self.assertIn("'fun' is a keyword", proc.stderr)
        os.makedirs(os.path.join(self.work, "taken"), exist_ok=True)
        proc = self.myla_cmd("new", "taken")
        self.assertEqual((proc.returncode, proc.stderr), (1, "myla: 'taken' exists already\n"))
        proc = self.myla_cmd("new")
        self.assertEqual(proc.returncode, 2)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestPathDependency(_Layout):
    """A project `app` with a path dependency `geo` and a nested module."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.geo = os.path.join(cls.work, "geo")
        cls.app = os.path.join(cls.work, "app")
        _write(os.path.join(cls.geo, "myla.toml"), GEO_MANIFEST)
        _write(os.path.join(cls.geo, "src", "geo.my"), GEO_LIB)
        _write(os.path.join(cls.geo, "src", "shapes.my"), GEO_SHAPES)
        _write(os.path.join(cls.app, "myla.toml"), APP_MANIFEST)
        _write(os.path.join(cls.app, "src", "main.my"), APP_MAIN)
        _write(os.path.join(cls.app, "src", "util", "strings.my"), APP_STRINGS)

    def run_in(self, cwd: str, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.myla, *argv], cwd=cwd, capture_output=True, text=True)

    def test_run_with_arguments(self):
        proc = self.run_in(self.app, "run", "x", "y z")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode),
                         ("12\n20\nhi!\nsrc/main.my\nx\ny z\n", "", 0))

    def test_run_from_a_subdirectory(self):
        proc = self.run_in(os.path.join(self.app, "src", "util"), "run")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode),
                         ("12\n20\nhi!\n../main.my\n", "", 0))

    def test_build_and_run_the_binary(self):
        proc = self.run_in(self.app, "build", "-g")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("", "", 0))
        run = subprocess.run([os.path.join(self.app, "build", "app"), "q"], capture_output=True, text=True)
        self.assertEqual(run.stdout, "12\n20\nhi!\n" + os.path.join(self.app, "build", "app") + "\nq\n")

    def test_test_runs_each_files_own_cases(self):
        proc = self.run_in(self.app, "test")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(proc.stdout,
                         "== src/main.my\nPASS  twice #1\n"
                         "== src/util/strings.my\nPASS  shout #1\nFAIL  shout #2: expected 'b?', got 'b!'\n"
                         "\n2/3 passed in 2 files.\n")
        proc = self.run_in(self.geo, "test")      # a library without a program
        self.assertEqual((proc.stderr, proc.returncode), ("", 0))
        self.assertEqual(proc.stdout,
                         "== src/geo.my\nPASS  area #1\n== src/shapes.my\nPASS  perimeter #1\n"
                         "\n2/2 passed in 2 files.\n")

    def test_check(self):
        proc = self.run_in(self.app, "check")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("", "", 0))
        proc = self.run_in(self.geo, "check")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("", "", 0))

    def test_a_library_has_no_program(self):
        proc = self.run_in(self.geo, "run")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, "myla: 'geo' has no program (src/main.my); `myla check` checks its library\n")
        proc = self.run_in(self.geo, "build")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("has no program", proc.stderr)

    def test_file_mode_reads_no_manifest(self):
        proc = self.run_in(self.app, "run", "src/main.my")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("cannot resolve import 'geo'", proc.stderr)
        proc = self.run_in(self.app, "run", "src/main.my", "--package", "geo=" + os.path.join(self.geo, "src"))
        self.assertEqual(proc.stdout, "12\n20\nhi!\nsrc/main.my\n")
        proc = self.run_in(self.app, "check", "src/util/strings.my")
        self.assertEqual((proc.stdout, proc.returncode), ("ok\n", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestProjectErrors(_Layout):
    def project(self, name: str, files: dict[str, str]) -> str:
        root = os.path.join(self.work, name)
        for rel, text in files.items():
            _write(os.path.join(root, rel), text)
        return root

    def run_in(self, cwd: str, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.myla, *argv], cwd=cwd, capture_output=True, text=True)

    def test_no_manifest(self):
        empty = os.path.join(self.work, "empty")
        os.makedirs(empty, exist_ok=True)
        for cmd in ("build", "run", "test", "check", "clean"):
            proc = self.run_in(empty, cmd)
            self.assertEqual((proc.stderr, proc.returncode),
                             ("myla: no myla.toml in this directory or above it\n", 1), cmd)

    def test_manifest_error(self):
        root = self.project("badtoml", {"myla.toml": '[package]\nname = "badtoml"\n', "src/main.my": "fun main() {}\n"})
        proc = self.run_in(root, "build")
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith("manifest error: "), proc.stderr)
        self.assertIn("version", proc.stderr)

    def test_compile_errors_name_the_file(self):
        root = self.project("broken", {
            "myla.toml": '[package]\nname = "broken"\nversion = "1"\n',
            "src/main.my": "fun main() {\n    print(nope)\n}\n",
            "src/ok.my": "pub fun f() -> int {\n    return 1\n}\n",
            "src/bad.my": "pub fun g() -> int {\n    return true\n}\n",
        })
        proc = self.run_in(root, "run")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--> src/main.my:2:11", proc.stderr)
        proc = self.run_in(root, "check")
        self.assertEqual((proc.stdout, proc.returncode), ("", 1))
        self.assertIn("--> src/bad.my:2:5", proc.stderr)
        self.assertIn("--> src/main.my:2:11", proc.stderr)
        self.assertNotIn("ok.my", proc.stderr)
        proc = self.run_in(root, "test")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--> src/bad.my:2:5", proc.stderr)
        self.assertEqual(proc.stdout, "no #test cases found.\n")

    def test_a_git_dependency_not_checked_out(self):
        commit = "4f3c2a1e9b0d5c6a7e8f9a0b1c2d3e4f5a6b7c8d"
        root = self.project("gitdep", {
            "myla.toml": '[package]\nname = "gitdep"\nversion = "1"\n\n[dependencies]\n'
                         'json5 = { git = "https://example.org/json5.git", tag = "v1" }\n',
            "myla.lock": f'version = 1\n\n[git.json5]\nurl = "https://example.org/json5.git"\ntag = "v1"\ncommit = "{commit}"\n',
            "src/main.my": "fun main() {}\n",
        })
        proc = self.run_in(root, "build")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("json5", proc.stderr)
        self.assertIn("myla fetch", proc.stderr)

    def test_usage_mentions_the_project_commands(self):
        proc = self.myla_cmd("nonsense")
        self.assertEqual(proc.returncode, 2)
        for cmd in ("new", "build", "run", "test", "check", "clean"):
            self.assertIn(f"  {cmd} ", proc.stderr)


if __name__ == "__main__":
    unittest.main()
