"""Burn test: Git dependencies and `myla fetch` (MYLA-95, D73).

`myla fetch` resolves each Git dependency without a current entry in
`myla.lock` (every one with `--update`) to a commit with `git ls-remote`,
checks it out into `.myla/deps/<name>-<commit>/` and writes the lock file;
`build`, `run`, `test` and `check` check out locked commits that are missing,
but never resolve references. The repositories are local, in temporary
directories, reached through `file://` URLs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from .test_selfhost_cli import _Layout

HAVE_GIT = shutil.which("git") is not None


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def git(cwd: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
         "-c", "init.defaultBranch=main", "-c", "tag.gpgSign=false", "-c", "commit.gpgSign=false", *args],
        cwd=cwd, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def library(root: str, name: str, greeting: str, deps: str = "") -> str:
    """A Git repository holding the package `name` whose `hello()` returns
    `greeting`; its URL."""
    _write(os.path.join(root, "myla.toml"),
           f'[package]\nname = "{name}"\nversion = "1"\n' + (f"\n[dependencies]\n{deps}" if deps else ""))
    _write(os.path.join(root, "src", f"{name}.my"), f'pub fun hello() -> str {{\n    return "{greeting}"\n}}\n')
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "first")
    return "file://" + root


def commit_greeting(root: str, name: str, greeting: str) -> str:
    _write(os.path.join(root, "src", f"{name}.my"), f'pub fun hello() -> str {{\n    return "{greeting}"\n}}\n')
    git(root, "commit", "-q", "-am", greeting)
    return git(root, "rev-parse", "HEAD")


APP_MAIN = """\
import greet

fun main() {
    print(greet.hello())
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE and HAVE_GIT, SKIP_REASON if not CAN_BUILD_NATIVE else "git is not installed")
class TestFetch(_Layout):
    def setUp(self) -> None:
        self.base = os.path.join(self.work, self.id().rsplit(".", 1)[-1])
        os.makedirs(self.base)

    def app(self, deps: str, main: str = APP_MAIN) -> str:
        root = os.path.join(self.base, "app")
        _write(os.path.join(root, "myla.toml"), f'[package]\nname = "app"\nversion = "1"\n\n[dependencies]\n{deps}')
        _write(os.path.join(root, "src", "main.my"), main)
        return root

    def run_in(self, cwd: str, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.myla, *argv], cwd=cwd, capture_output=True, text=True)

    def lock(self, root: str) -> str:
        with open(os.path.join(root, "myla.lock"), encoding="utf-8") as fh:
            return fh.read()

    def test_tags_lightweight_and_annotated(self):
        repo = os.path.join(self.base, "greet")
        url = library(repo, "greet", "one")
        v1 = git(repo, "rev-parse", "HEAD")
        git(repo, "tag", "v1")
        v2 = commit_greeting(repo, "greet", "two")
        git(repo, "tag", "-a", "v2", "-m", "the second")
        app = self.app(f'greet = {{ git = "{url}", tag = "v1" }}\n')

        proc = self.run_in(app, "fetch")
        self.assertEqual((proc.stdout, proc.returncode), ("", 0), proc.stderr)
        self.assertEqual(proc.stderr, f"fetching greet tag v1 ({v1[:7]})\n")
        self.assertEqual(self.lock(app),
                         "# Written by `myla fetch`. Commit it; don't edit it.\nversion = 1\n\n"
                         f'[git.greet]\nurl = "{url}"\ntag = "v1"\ncommit = "{v1}"\n')
        self.assertTrue(os.path.isfile(os.path.join(app, ".myla", "deps", f"greet-{v1}", "src", "greet.my")))
        proc = self.run_in(app, "run")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("one\n", "", 0))

        # an annotated tag resolves to its commit, not to the tag object
        _write(os.path.join(app, "myla.toml"),
               f'[package]\nname = "app"\nversion = "1"\n\n[dependencies]\ngreet = {{ git = "{url}", tag = "v2" }}\n')
        proc = self.run_in(app, "run")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("dependency 'greet' is not locked: run `myla fetch`", proc.stderr)
        proc = self.run_in(app, "fetch")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, f"fetching greet tag v2 ({v2[:7]})\n")
        self.assertIn(f'commit = "{v2}"', self.lock(app))
        self.assertNotIn(v1, self.lock(app))
        proc = self.run_in(app, "run")
        self.assertEqual(proc.stdout, "two\n")

    def test_a_branch_moves_only_with_update(self):
        repo = os.path.join(self.base, "greet")
        url = library(repo, "greet", "old")
        first = git(repo, "rev-parse", "HEAD")
        app = self.app(f'greet = {{ git = "{url}", branch = "main" }}\n')
        self.assertEqual(self.run_in(app, "fetch").returncode, 0)
        self.assertIn(f'commit = "{first}"', self.lock(app))
        second = commit_greeting(repo, "greet", "new")
        proc = self.run_in(app, "fetch")              # the lock entry is current
        self.assertEqual((proc.stderr, proc.returncode), ("", 0))
        self.assertIn(f'commit = "{first}"', self.lock(app))
        self.assertEqual(self.run_in(app, "run").stdout, "old\n")
        proc = self.run_in(app, "fetch", "--update")
        self.assertEqual((proc.stderr, proc.returncode), (f"fetching greet branch main ({second[:7]})\n", 0))
        self.assertIn(f'commit = "{second}"', self.lock(app))
        self.assertEqual(self.run_in(app, "run").stdout, "new\n")

    def test_the_default_branch_and_a_rev(self):
        repo = os.path.join(self.base, "greet")
        url = library(repo, "greet", "first")
        first = git(repo, "rev-parse", "HEAD")
        head = commit_greeting(repo, "greet", "head")
        app = self.app(f'greet = {{ git = "{url}" }}\n')
        self.assertEqual(self.run_in(app, "fetch").stderr, f"fetching greet ({head[:7]})\n")
        self.assertEqual(self.run_in(app, "run").stdout, "head\n")
        app2 = os.path.join(self.base, "app2")
        _write(os.path.join(app2, "myla.toml"),
               f'[package]\nname = "app2"\nversion = "1"\n\n[dependencies]\ngreet = {{ git = "{url}", rev = "{first}" }}\n')
        _write(os.path.join(app2, "src", "main.my"), APP_MAIN)
        proc = self.run_in(app2, "fetch")
        self.assertEqual((proc.stderr, proc.returncode), (f"fetching greet rev {first} ({first[:7]})\n", 0))
        self.assertEqual(self.run_in(app2, "run").stdout, "first\n")

    def test_commands_check_out_locked_commits(self):
        repo = os.path.join(self.base, "greet")
        url = library(repo, "greet", "hi")
        commit = git(repo, "rev-parse", "HEAD")
        app = self.app(f'greet = {{ git = "{url}" }}\n')
        self.assertEqual(self.run_in(app, "fetch").returncode, 0)
        shutil.rmtree(os.path.join(app, ".myla"))
        # an interrupted checkout is cloned again
        partial = os.path.join(app, ".myla", "deps", f"greet-{commit}.partial")
        os.makedirs(partial)
        _write(os.path.join(partial, "junk"), "x")
        proc = self.run_in(app, "build")
        self.assertEqual((proc.stdout, proc.returncode), ("", 0), proc.stderr)
        self.assertEqual(proc.stderr, f"fetching greet ({commit[:7]})\n")
        self.assertFalse(os.path.exists(partial))
        run = subprocess.run([os.path.join(app, "build", "app")], capture_output=True, text=True)
        self.assertEqual(run.stdout, "hi\n")
        proc = self.run_in(app, "clean", "--deps")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(app, ".myla")))
        self.assertFalse(os.path.exists(os.path.join(app, "build")))

    def test_a_dependency_of_a_dependency(self):
        inner = os.path.join(self.base, "inner")
        inner_url = library(inner, "inner", "deep")
        inner_commit = git(inner, "rev-parse", "HEAD")
        outer = os.path.join(self.base, "greet")
        _write(os.path.join(outer, "myla.toml"),
               f'[package]\nname = "greet"\nversion = "1"\n\n[dependencies]\ninner = {{ git = "{inner_url}" }}\n')
        _write(os.path.join(outer, "src", "greet.my"), "import inner\n\npub fun hello() -> str {\n    return inner.hello() + \"!\"\n}\n")
        git(outer, "init", "-q")
        git(outer, "add", "-A")
        git(outer, "commit", "-q", "-m", "outer")
        outer_commit = git(outer, "rev-parse", "HEAD")
        app = self.app(f'greet = {{ git = "file://{outer}" }}\n')
        proc = self.run_in(app, "fetch")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, f"fetching greet ({outer_commit[:7]})\nfetching inner ({inner_commit[:7]})\n")
        lock = self.lock(app)
        self.assertIn("[git.greet]", lock)
        self.assertIn("[git.inner]", lock)
        self.assertLess(lock.index("[git.greet]"), lock.index("[git.inner]"))
        self.assertEqual(self.run_in(app, "run").stdout, "deep!\n")

    def test_errors(self):
        repo = os.path.join(self.base, "greet")
        url = library(repo, "greet", "x")
        app = self.app(f'greet = {{ git = "{url}", tag = "nope" }}\n')
        proc = self.run_in(app, "fetch")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, f"myla: dependency 'greet': there is no tag 'nope' in {url}\n")
        self.assertFalse(os.path.exists(os.path.join(app, "myla.lock")))

        missing = "file://" + os.path.join(self.base, "nowhere")
        app = self.app(f'greet = {{ git = "{missing}" }}\n')
        proc = self.run_in(app, "fetch")
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith(f"myla: dependency 'greet': git ls-remote {missing} failed\n"), proc.stderr)

        app = self.app(f'greet = {{ git = "{url}", rev = "{"0" * 40}" }}\n')
        proc = self.run_in(app, "fetch")
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"myla: dependency 'greet': cannot check out commit {'0' * 40} from {url}", proc.stderr)

    def test_two_versions_of_a_package(self):
        repo = os.path.join(self.base, "greet")
        url = library(repo, "greet", "x")
        other = os.path.join(self.base, "other")
        _write(os.path.join(other, "myla.toml"),
               f'[package]\nname = "other"\nversion = "1"\n\n[dependencies]\ngreet = {{ path = "{repo}" }}\n')
        _write(os.path.join(other, "src", "other.my"), "pub fun f() -> int {\n    return 1\n}\n")
        app = self.app(f'greet = {{ git = "{url}" }}\nother = {{ path = "../other" }}\n')
        proc = self.run_in(app, "fetch")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("two versions of package 'greet'", proc.stderr)

    def test_no_git_dependencies_writes_no_lock(self):
        app = self.app("", main="fun main() {\n    print(1)\n}\n")
        proc = self.run_in(app, "fetch")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("", "", 0))
        self.assertFalse(os.path.exists(os.path.join(app, "myla.lock")))


if __name__ == "__main__":
    unittest.main()
