"""Burn tests: the project model of the project tool (MYLA-93).

`selfhost/project_main.my` finds `myla.toml` from its working directory
upwards, resolves the project with `selfhost/project.my` and prints it (or
the error, as the CLI prints it). Each test writes packages into a fresh
temporary directory and runs the driver there: every manifest and lock file
error once, transitive path dependencies, cycles, the one-version rule, and
Git dependencies that are locked and checked out (the checkout made by hand),
unlocked, or locked but not checked out yet. Lock files round-trip through
`render_lock`.

The driver is built by the Python backend; a few scenarios also run in the
Python interpreter and in the driver built by the self-hosted backend, which
must print the same.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

from myla.loader import default_stdlib_root

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

C1 = "4f3c2a1e9b0d5c6a7e8f9a0b1c2d3e4f5a6b7c8d"
C2 = "0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c"
LOCK_HEADER = "# Written by `myla fetch`. Commit it; don't edit it.\nversion = 1\n"


def manifest(name: str, deps: str = "", version: str = "0.1.0") -> str:
    text = f'[package]\nname = "{name}"\nversion = "{version}"\n'
    if deps:
        text += "[dependencies]\n" + deps
    return text


def library(name: str, deps: str = "", version: str = "0.1.0") -> dict[str, str]:
    """A package with a library, as files below its directory."""
    return {"myla.toml": manifest(name, deps, version), f"src/{name}.my": "pub fun f() -> int { return 1 }\n"}


def under(prefix: str, files: dict[str, str]) -> dict[str, str]:
    return {f"{prefix}/{k}": v for k, v in files.items()}


APP = {"app/src/main.my": "fun main() {}\n"}


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class ProjectModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = selfhost_tool("project_main")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.count = 0

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def make(self, files: dict[str, str], dirs: tuple[str, ...] = ()) -> str:
        """A fresh directory (its real path) holding `files` and `dirs`."""
        type(self).count += 1
        root = os.path.realpath(os.path.join(self.tmp.name, f"t{self.count}"))
        os.makedirs(root)
        for d in dirs:
            os.makedirs(os.path.join(root, d), exist_ok=True)
        for rel, text in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return root

    def run_tool(self, root: str, cwd: str = "app", args: tuple[str, ...] = (), argv=None) -> tuple[str, str, int]:
        command = argv if argv is not None else [self.tool]
        proc = subprocess.run([*command, *args], cwd=os.path.join(root, cwd),
                              capture_output=True, timeout=120)
        return (proc.stdout.decode().replace(root, "{root}"),
                proc.stderr.decode().replace(root, "{root}"), proc.returncode)

    def project(self, files: dict[str, str], dirs: tuple[str, ...] = (), cwd: str = "app",
                args: tuple[str, ...] = ()) -> str:
        out, err, code = self.run_tool(self.make(files, dirs), cwd, args)
        self.assertEqual((err, code), ("", 0), out)
        return out

    def error(self, files: dict[str, str], dirs: tuple[str, ...] = (), cwd: str = "app") -> str:
        out, err, code = self.run_tool(self.make(files, dirs), cwd)
        self.assertEqual((out, code), ("", 1), err)
        return err

    def assert_error(self, files: dict[str, str], message: str, where: str = "", dirs: tuple[str, ...] = ()) -> None:
        """The first two lines of the error: `message` (with its kind) and,
        if given, `  --> {root}/<where>`."""
        lines = self.error(files, dirs).splitlines()
        self.assertEqual(lines[0], message)
        if where:
            self.assertEqual(lines[1], f"  --> {{root}}/{where}")
        else:
            self.assertEqual(len(lines), 1, lines)

    # --- resolving ---------------------------------------------------------------

    def test_transitive_path_dependencies_from_a_subdirectory(self) -> None:
        files = {
            **under("app", library("app", 'util = { path = "../libs/util" }\ngeo = { path = "../libs/geo" }\n')),
            **APP,
            **under("libs/geo", library("geo", 'util = { path = "../util" }\n', "2.0.0")),
            **under("libs/util", library("util", "", "0.3.0")),
            "libs/util/src/main.my": "fun main() {}\n",
        }
        out = self.project(files, dirs=("app/src/deep/er",), cwd="app/src/deep/er")
        self.assertEqual(out, (
            "manifest {root}/app/myla.toml\n"
            "root app 0.1.0 root {root}/app program library\n"
            "dep geo 2.0.0 path {root}/libs/geo library\n"
            "dep util 0.3.0 path {root}/libs/util program library\n"
            "--package geo={root}/libs/geo/src\n"
            "--package util={root}/libs/util/src\n"))

    def test_nearest_manifest_wins(self) -> None:
        files = {**under("app", library("app")), **under("app/inner", library("inner"))}
        out = self.project(files, cwd="app/inner/src")
        self.assertEqual(out.splitlines()[:2], [
            "manifest {root}/app/inner/myla.toml",
            "root inner 0.1.0 root {root}/app/inner library"])

    def test_no_manifest(self) -> None:
        root = self.make({}, dirs=("app",))
        self.assertEqual(self.run_tool(root), ("", "myla: no myla.toml in this directory or above it\n", 1))

    def test_absolute_path_and_a_program_without_library(self) -> None:
        root = self.make({**under("geo", library("geo")), "app/src/main.my": "fun main() {}\n"})
        with open(os.path.join(root, "app", "myla.toml"), "w", encoding="utf-8") as fh:
            fh.write(manifest("app", f'geo = {{ path = "{root}/./geo/" }}\n'))
        out, err, code = self.run_tool(root)
        self.assertEqual((err, code), ("", 0))
        self.assertEqual(out.splitlines()[1:3], [
            "root app 0.1.0 root {root}/app program",
            "dep geo 0.1.0 path {root}/geo library"])

    def test_cycles_are_allowed(self) -> None:
        # geo and util need each other, and util needs the root package back
        files = {
            **under("app", library("app", 'geo = { path = "../geo" }\n')),
            **under("geo", library("geo", 'util = { path = "../util" }\n')),
            **under("util", library("util", 'geo = { path = "../geo" }\napp = { path = "../app/" }\n')),
        }
        self.assertEqual(self.project(files).splitlines()[2:4], [
            "dep geo 0.1.0 path {root}/geo library",
            "dep util 0.1.0 path {root}/util library"])

    def test_a_cycle_back_to_the_root_needs_its_library(self) -> None:
        files = {
            "app/myla.toml": manifest("app", 'geo = { path = "../geo" }\n'), **APP,
            **under("geo", library("geo", 'app = { path = "../app" }\n')),
        }
        self.assert_error(files, "manifest error: dependency 'app' has no library (src/app.my)", "geo/myla.toml:5:1")

    def test_two_versions(self) -> None:
        files = {
            **under("app", library("app", 'geo = { path = "../geo" }\nutil = { path = "../util" }\n')),
            **under("geo", library("geo", 'util = { path = "../util2" }\n')),
            **under("util", library("util")),
            **under("util2", library("util")),
        }
        self.assertEqual(self.error(files), (
            "manifest error: two versions of package 'util': path ../util (required by app)"
            " and path ../util2 (required by geo)\n"
            "  --> {root}/geo/myla.toml:5:1\n"
            "  |\n"
            '5 | util = { path = "../util2" }\n'
            "  | ^^^^\n"))

    def test_two_versions_of_the_root_package(self) -> None:
        files = {
            **under("app", library("app", 'geo = { path = "../geo" }\n')),
            **under("geo", library("geo", 'app = { git = "https://example.org/app.git" }\n')),
        }
        self.assert_error(files, "manifest error: two versions of package 'app': the root package and"
                          " git https://example.org/app.git (required by geo)", "geo/myla.toml:5:1")

    def test_same_directory_spelt_differently_is_one_version(self) -> None:
        files = {
            **under("app", library("app", 'geo = { path = "../geo" }\nutil = { path = "../util" }\n')),
            **under("geo", library("geo", 'util = { path = "../x/../util/." }\n')),
            **under("util", library("util")),
        }
        self.assertIn("dep util 0.1.0 path {root}/util library", self.project(files))

    def test_name_mismatch(self) -> None:
        files = {**under("app", library("app", 'geo = { path = "../geo" }\n')),
                 **under("geo", library("geometry"))}
        self.assert_error(files, "manifest error: dependency 'geo' is named 'geometry' in its myla.toml",
                          "app/myla.toml:5:1")

    def test_missing_library(self) -> None:
        files = {**under("app", library("app", 'geo = { path = "../geo" }\n')),
                 "geo/myla.toml": manifest("geo"), "geo/src/main.my": "fun main() {}\n"}
        self.assert_error(files, "manifest error: dependency 'geo' has no library (src/geo.my)", "app/myla.toml:5:1")

    def test_missing_package_directory(self) -> None:
        files = under("app", library("app", 'geo = { path = "../geo" }\n'))
        self.assert_error(files, "manifest error: dependency 'geo' has no myla.toml in {root}/geo", "app/myla.toml:5:1")

    def test_errors_in_a_dependency_manifest_name_its_file(self) -> None:
        files = {**under("app", library("app", 'geo = { path = "../geo" }\n')),
                 **under("geo", library("geo")), "geo/myla.toml": '[package]\nname = "geo"\n'}
        self.assert_error(files, "manifest error: missing 'version' in [package]", "geo/myla.toml:1:1")

    # --- manifest errors ---------------------------------------------------------

    def test_syntax_error(self) -> None:
        self.assertEqual(self.error({"app/myla.toml": '[package]\nname = "app\n'}), (
            "manifest error: unterminated string\n"
            "  --> {root}/app/myla.toml:2:8\n"
            "  |\n"
            '2 | name = "app\n'
            "  |        ^\n"))

    def test_missing_package_table(self) -> None:
        self.assert_error({"app/myla.toml": "[dependencies]\n"}, "myla: {root}/app/myla.toml: missing table [package]")

    def test_package_must_be_a_table(self) -> None:
        self.assert_error({"app/myla.toml": 'package = "app"\n'}, "manifest error: 'package' must be a table",
                          "app/myla.toml:1:11")

    def test_missing_name(self) -> None:
        self.assert_error({"app/myla.toml": '# c\n[package]\nversion = "1"\n'},
                          "manifest error: missing 'name' in [package]", "app/myla.toml:2:1")

    def test_missing_version(self) -> None:
        self.assert_error({"app/myla.toml": '[package]\nname = "app"\n'},
                          "manifest error: missing 'version' in [package]", "app/myla.toml:1:1")

    def test_version_must_be_a_string(self) -> None:
        self.assert_error({"app/myla.toml": '[package]\nname = "app"\nversion = 1\n'},
                          "manifest error: 'package.version' must be a string", "app/myla.toml:3:11")

    def test_authors_must_be_strings(self) -> None:
        text = '[package]\nname = "app"\nversion = "1"\nauthors = "Ada"\n'
        self.assert_error({"app/myla.toml": text}, "manifest error: 'package.authors' must be an array of strings",
                          "app/myla.toml:4:11")

    def test_optional_fields(self) -> None:
        text = ('[package]\nname = "app"\nversion = "1"\ndescription = "d"\nlicense = "MIT"\n'
                'authors = ["Ada <ada@example.org>"]\n')
        self.assertIn("root app 1 root {root}/app\n", self.project({"app/myla.toml": text}))

    def test_bad_name(self) -> None:
        self.assertEqual(self.error({"app/myla.toml": '[package]\nname = "1app"\nversion = "1"\n'}), (
            "manifest error: '1app' is not a valid package name: it must be an ASCII letter followed by"
            " ASCII letters, digits and '_'\n"
            "  --> {root}/app/myla.toml:2:8\n"
            "  |\n"
            '2 | name = "1app"\n'
            "  |        ^^^^^^\n"))

    def test_keyword_name(self) -> None:
        self.assert_error({"app/myla.toml": '[package]\nname = "while"\nversion = "1"\n'},
                          "manifest error: 'while' is a keyword and can't be a package name", "app/myla.toml:2:8")

    def test_std_name(self) -> None:
        self.assert_error({"app/myla.toml": manifest("app", 'std = { path = "../std" }\n')},
                          "manifest error: 'std' is the standard library and can't be a package name",
                          "app/myla.toml:5:1")

    def test_unknown_key(self) -> None:
        self.assert_error({"app/myla.toml": '[package]\nnmae = "app"\n'},
                          "manifest error: unknown key 'nmae' in [package]", "app/myla.toml:2:1")

    def test_unknown_table(self) -> None:
        self.assert_error({"app/myla.toml": manifest("app") + '[dependecies]\ngeo = { path = "../geo" }\n'},
                          "manifest error: unknown table 'dependecies'", "app/myla.toml:4:1")

    def test_unknown_dependency_key(self) -> None:
        self.assert_error({"app/myla.toml": manifest("app", 'geo = { path = "../geo", version = "1" }\n')},
                          "manifest error: unknown key 'version' in dependency 'geo'", "app/myla.toml:5:26")

    def test_path_and_git(self) -> None:
        self.assert_error({"app/myla.toml": manifest("app", 'geo = { path = "../geo", git = "https://x" }\n')},
                          "manifest error: dependency 'geo' has both 'path' and 'git'", "app/myla.toml:5:1")

    def test_neither_path_nor_git(self) -> None:
        text = manifest("app") + '\n[dependencies.geo]\ntag = "v1"\n'
        self.assert_error({"app/myla.toml": text}, "manifest error: dependency 'geo' needs 'path' or 'git'",
                          "app/myla.toml:5:1")

    def test_two_references(self) -> None:
        self.assert_error({"app/myla.toml": manifest("app", 'geo = { git = "https://x", tag = "a", branch = "b" }\n')},
                          "manifest error: dependency 'geo' has both 'tag' and 'branch': give at most one of"
                          " 'tag', 'branch' and 'rev'", "app/myla.toml:5:39")

    def test_reference_with_path(self) -> None:
        self.assert_error({"app/myla.toml": manifest("app", 'geo = { path = "../geo", tag = "v1" }\n')},
                          "manifest error: 'tag' of dependency 'geo' needs 'git', not 'path'", "app/myla.toml:5:26")

    def test_short_rev(self) -> None:
        self.assert_error({"app/myla.toml": manifest("app", 'geo = { git = "https://x", rev = "4f3c2a1" }\n')},
                          "manifest error: 'rev' of dependency 'geo' must be a full commit id (40 hexadecimal digits)",
                          "app/myla.toml:5:34")

    def test_no_shorthand(self) -> None:
        self.assert_error({"app/myla.toml": manifest("app", 'geo = "1.0"\n')},
                          "manifest error: dependency 'geo' must be a table, such as geo = { path = \"../geo\" }",
                          "app/myla.toml:5:7")

    def test_empty_path(self) -> None:
        self.assert_error({"app/myla.toml": manifest("app", 'geo = { path = "" }\n')},
                          "manifest error: 'path' of dependency 'geo' is empty", "app/myla.toml:5:16")

    def test_bad_dependency_name(self) -> None:
        self.assert_error({"app/myla.toml": manifest("app", '"my-geo" = { path = "../geo" }\n')},
                          "manifest error: 'my-geo' is not a valid package name: it must be an ASCII letter followed"
                          " by ASCII letters, digits and '_'", "app/myla.toml:5:1")

    # --- Git dependencies --------------------------------------------------------

    JSON5_DEP = 'json5 = { git = "https://example.org/json5.git", tag = "v1.2.0" }\n'
    GIT_APP = manifest("app", JSON5_DEP)
    JSON5_LOCK = (LOCK_HEADER + "\n[git.json5]\nurl = \"https://example.org/json5.git\"\n"
                  f'tag = "v1.2.0"\ncommit = "{C1}"\n')

    def test_git_locked_and_checked_out(self) -> None:
        checkout = f"app/.myla/deps/json5-{C1}"
        files = {
            "app/myla.toml": self.GIT_APP, "app/myla.lock": self.JSON5_LOCK, **APP,
            # a path dependency inside the checkout, and a path dependency of
            # the root package that the Git package also needs (the same one)
            **under(checkout, library("json5", 'inner = { path = "vendor/inner" }\n', "1.2.0")),
            **under(checkout + "/vendor/inner", library("inner")),
        }
        out = self.project(files)
        self.assertEqual(out, (
            "manifest {root}/app/myla.toml\n"
            "root app 0.1.0 root {root}/app program\n"
            f"dep inner 0.1.0 path {{root}}/{checkout}/vendor/inner library\n"
            f"dep json5 1.2.0 git https://example.org/json5.git tag v1.2.0 {C1} {{root}}/{checkout} library\n"
            f"--package inner={{root}}/{checkout}/vendor/inner/src\n"
            f"--package json5={{root}}/{checkout}/src\n"))

    def test_git_path_dependency_must_stay_in_its_checkout(self) -> None:
        checkout = f"app/.myla/deps/json5-{C1}"
        files = {
            "app/myla.toml": self.GIT_APP, "app/myla.lock": self.JSON5_LOCK,
            **under(checkout, library("json5", 'up = { path = "../../../../up" }\n')),
            **under("up", library("up")),
        }
        self.assert_error(files, "manifest error: path dependency 'up' of 'json5' is outside its Git checkout",
                          f"{checkout}/myla.toml:5:1")

    def test_git_unlocked(self) -> None:
        self.assertEqual(self.error({"app/myla.toml": self.GIT_APP}), (
            "manifest error: dependency 'json5' is not locked: run `myla fetch`\n"
            "  --> {root}/app/myla.toml:5:1\n"
            "  |\n"
            '5 | json5 = { git = "https://example.org/json5.git", tag = "v1.2.0" }\n'
            "  | ^^^^^\n"))

    def test_git_lock_entry_not_current(self) -> None:
        # the lock file pins another reference: that entry isn't current
        stale = self.JSON5_LOCK.replace('tag = "v1.2.0"', 'tag = "v1.1.0"')
        self.assert_error({"app/myla.toml": self.GIT_APP, "app/myla.lock": stale},
                          "manifest error: dependency 'json5' is not locked: run `myla fetch`", "app/myla.toml:5:1")

    def test_git_unlocked_as_fetch_sees_it(self) -> None:
        files = {"app/myla.toml": manifest("app", 'geo = { path = "../geo" }\n'),
                 **under("geo", library("geo", 'color = { git = "https://example.org/color.git", branch = "main" }\n'))}
        out = self.project(files, args=("--fetch",))
        self.assertEqual(out, (
            "manifest {root}/app/myla.toml\n"
            "root app 0.1.0 root {root}/app\n"
            "dep geo 0.1.0 path {root}/geo library\n"
            "unlocked color git https://example.org/color.git branch main\n"
            "--package geo={root}/geo/src\n"
            "-- myla.lock\n" + LOCK_HEADER))

    def test_git_checkout_missing(self) -> None:
        files = {"app/myla.toml": self.GIT_APP, "app/myla.lock": self.JSON5_LOCK}
        out = self.project(files)
        self.assertEqual(out, (
            "manifest {root}/app/myla.toml\n"
            "root app 0.1.0 root {root}/app\n"
            f"missing json5 git https://example.org/json5.git tag v1.2.0 {C1} {{root}}/app/.myla/deps/json5-{C1}\n"))
        # `myla fetch` keeps the current entry and drops the others
        extra = self.JSON5_LOCK + f'\n[git.old]\nurl = "https://example.org/old.git"\ncommit = "{C2}"\n'
        out = self.project({**files, "app/myla.lock": extra}, args=("--fetch",))
        self.assertTrue(out.endswith("-- myla.lock\n" + self.JSON5_LOCK), out)

    def test_git_default_branch_and_rev(self) -> None:
        deps = (f'a = {{ git = "https://example.org/a.git" }}\n'
                f'b = {{ git = "https://example.org/b.git", rev = "{C2.upper()}" }}\n')
        lock = (LOCK_HEADER + f'\n[git.b]\nurl = "https://example.org/b.git"\nrev = "{C2.upper()}"\ncommit = "{C2}"\n'
                f'\n[git.a]\nurl = "https://example.org/a.git"\ncommit = "{C1}"\n')
        files = {"app/myla.toml": manifest("app", deps), "app/myla.lock": lock,
                 **under(f"app/.myla/deps/a-{C1}", library("a")), **under(f"app/.myla/deps/b-{C2}", library("b"))}
        out = self.project(files)
        self.assertIn(f"dep a 0.1.0 git https://example.org/a.git {C1} {{root}}/app/.myla/deps/a-{C1} library\n", out)
        self.assertIn(f"dep b 0.1.0 git https://example.org/b.git rev {C2.upper()} {C2} "
                      f"{{root}}/app/.myla/deps/b-{C2} library\n", out)

    # --- the lock file -----------------------------------------------------------

    DESIGN_LOCK = (LOCK_HEADER + "\n[git.color]\nurl = \"https://example.org/color.git\"\nbranch = \"main\"\n"
                   f'commit = "{C2}"\n\n[git.json5]\nurl = "https://github.com/example/json5-myla.git"\n'
                   f'tag = "v1.2.0"\ncommit = "{C1}"\n')

    def lock(self, text: str) -> tuple[str, str, int]:
        root = self.make({"app/myla.lock": text})
        return self.run_tool(root, args=("--lock", "myla.lock"))

    def test_lock_round_trip(self) -> None:
        self.assertEqual(self.lock(self.DESIGN_LOCK), (self.DESIGN_LOCK, "", 0))
        self.assertEqual(self.lock(LOCK_HEADER), (LOCK_HEADER, "", 0))

    def test_lock_is_written_sorted_and_canonical(self) -> None:
        messy = ("version = 1  # format\n[git.json5]\ncommit = '" + C1 + "'\ntag = \"v1.2.0\"\n"
                 "url = \"https://github.com/example/json5-myla.git\"\n"
                 "[git.color]\nurl = \"https://example.org/color.git\"\nbranch = \"main\"\ncommit = \"" + C2 + "\"\n")
        self.assertEqual(self.lock(messy), (self.DESIGN_LOCK, "", 0))

    def test_lock_errors(self) -> None:
        cases = {
            "version = 2\n": "lock file error: myla.lock is from a newer myla\n  --> myla.lock:1:11",
            "version = 0\n": "lock file error: unknown lock file version 0\n  --> myla.lock:1:11",
            "": "myla: myla.lock: the lock file has no 'version'",
            "version = 1\npackages = 1\n": "lock file error: unknown key 'packages' in the lock file\n"
                                           "  --> myla.lock:2:1",
            "version = 1\n[git.a]\nurl = \"u\"\ncommit = \"abc\"\n":
                "lock file error: 'commit' of [git.a] must be 40 hexadecimal digits\n  --> myla.lock:4:10",
            f"version = 1\n[git.a]\ncommit = \"{C1}\"\n": "lock file error: missing 'url' in [git.a]\n"
                                                           "  --> myla.lock:2:1",
            "version = 1\n[git.a]\nurl = \"u\"\n": "lock file error: missing 'commit' in [git.a]\n"
                                                  "  --> myla.lock:2:1",
            "version = 1\n[git.a]\nurl = \"u\"\nhash = \"x\"\n": "lock file error: unknown key 'hash' in [git.a]\n"
                                                               "  --> myla.lock:4:1",
            "version = \"1\"\n": "lock file error: 'version' must be an integer\n  --> myla.lock:1:11",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                out, err, code = self.lock(text)
                self.assertEqual((out, code), ("", 1))
                self.assertEqual("\n".join(err.splitlines()[:2]), expected)

    def test_a_broken_lock_file_stops_the_build(self) -> None:
        files = {"app/myla.toml": self.GIT_APP, "app/myla.lock": "version = 3\n"}
        self.assert_error(files, "lock file error: myla.lock is from a newer myla", "app/myla.lock:1:11")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class ProjectModelParity(unittest.TestCase):
    """A project with every kind of package, an error, and a lock file print
    the same in the Python interpreter and the drivers built by both
    backends."""

    def test_parity(self) -> None:
        gen = selfhost_tool("gen_main")
        source = os.path.join(_REPO, "selfhost", "project_main.my")
        with tempfile.TemporaryDirectory() as tmp:
            sh_native = os.path.join(tmp, "sh_native")
            asm = subprocess.run([gen, source, default_stdlib_root()], capture_output=True, text=True, check=True)
            with open(sh_native + ".s", "w", encoding="utf-8") as fh:
                fh.write(asm.stdout)
            subprocess.run(["as", "--64", "-o", sh_native + ".o", sh_native + ".s"], check=True)
            subprocess.run(["ld", "-o", sh_native, sh_native + ".o"], check=True)
            drivers = {
                "python native": [selfhost_tool("project_main")],
                "python interpreter": [sys.executable, os.path.join(_REPO, "myla.py"), "run", source],
                "self-hosted native": [sh_native],
            }
            root = os.path.realpath(os.path.join(tmp, "p"))
            checkout = f"app/.myla/deps/json5-{C1}"
            files = {
                **under("app", library("app", 'geo = { path = "../geo" }\n' + ProjectModel.JSON5_DEP)),
                "app/myla.lock": ProjectModel.JSON5_LOCK, **APP,
                **under("geo", library("geo", 'app = { path = "../app" }\ncolor = { git = "https://example.org/c.git" }\n')),
                **under(checkout, library("json5", "", "1.2.0")),
                "bad/myla.toml": '[package]\nname = "größe"\nversion = "1"\n',
            }
            for rel, text in files.items():
                path = os.path.join(root, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            runs = [("app", ("--fetch",)), ("app", ()), ("bad", ()), ("app", ("--lock", "myla.lock"))]
            results = {}
            for name, argv in drivers.items():
                outs = []
                for cwd, args in runs:
                    proc = subprocess.run([*argv, *args], cwd=os.path.join(root, cwd), capture_output=True, timeout=300)
                    outs.append((proc.stdout.decode(), proc.stderr.decode(), proc.returncode))
                results[name] = outs
        expected = results["python native"]
        self.assertIn("unlocked color git https://example.org/c.git\n", expected[0][0])
        self.assertIn("dependency 'color' is not locked", expected[1][1])
        self.assertIn("'größe' is not a valid package name", expected[2][1])
        self.assertEqual(expected[3], (ProjectModel.JSON5_LOCK, "", 0))
        for name, outs in results.items():
            with self.subTest(driver=name):
                self.assertEqual(outs, expected)


if __name__ == "__main__":
    unittest.main()
