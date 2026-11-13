"""Burn test: the parse of the standard library the toolchain carries (MYLA-412).

`tools/embed/main.my` writes into `selfhost/embedded_std.my`, beside each
module of `std`, the module's parse with its functions' bodies left for later
(`selfhost/astcache.my`, the implicit modules' bodies parsed too), and the
loader reads it instead of the file whenever the file's text is the embedded
one: the built-in library, or a `--stdlib` directory with the same text.
Reading it must change nothing. So every example and the compiler are built
here twice with one library directory: as it is (its texts are the embedded
ones, so the loader reads the parse), and with one more newline at the end of
each module (another text, so the loader parses the files as before), and
the binaries must be the same bytes, on every target; the error corpus's
messages and a runtime error inside a body of the library must be the same.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

# a runtime error inside a body of std.list, which the loader reads late:
# its message names the place in the library's file (std.option's `expect`
# reports its caller's position since MYLA-435)
PANIC = """fun main() {
    let xs = [3, 1, 2]
    print(xs.sorted()[0])
    let n = 0
    print(xs.chunks(n).len())
}
"""

# the examples built for the other targets too (all of them build for x86-64)
OTHER_TARGETS = ["aarch64-linux", "wasm32-wasi"]
ON_EVERY_TARGET = ["hello.my", "maps.my", "strings.my", "slices_and_formats.my", "traits_on_builtins.my"]


def _programs() -> list[str]:
    """Every example with a `main` (not the error corpus), and the compiler."""
    out = []
    for path in sorted(glob.glob(os.path.join(_REPO, "examples", "**", "*.my"), recursive=True)):
        if os.sep + "errors" + os.sep in path:
            continue
        with open(path, encoding="utf-8") as fh:
            if "fun main" in fh.read():
                out.append(path)
    out.append(os.path.join(_REPO, "selfhost", "main.my"))
    return out


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class WithAndWithoutTheCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.myla = selfhost_tool("main")
        cls.tmp = tempfile.mkdtemp(prefix="myla-std-cache-")
        cls.lib = os.path.join(cls.tmp, "lib")
        shutil.copytree(STDLIB_ROOT, cls.lib)
        cls.panic = os.path.join(cls.tmp, "panic.my")
        with open(cls.panic, "w", encoding="utf-8") as fh:
            fh.write(PANIC)
        cls.carried = cls._outcomes("carried")
        for path in glob.glob(os.path.join(cls.lib, "std", "**", "*.my"), recursive=True):
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n")
        cls.parsed = cls._outcomes("parsed")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def _run(cls, args: list[str]) -> tuple[int, str, str]:
        p = subprocess.run([cls.myla, *args, "--stdlib", cls.lib], capture_output=True, text=True, cwd=_REPO)
        return (p.returncode, p.stdout, p.stderr)

    @classmethod
    def _outcomes(cls, mode: str) -> dict[str, object]:
        out: dict[str, object] = {}
        # the same output path for both, as a binary names its object file
        bins = os.path.join(cls.tmp, "bin")
        os.makedirs(bins, exist_ok=True)
        builds = [(p, None) for p in _programs()]
        builds += [(os.path.join(_REPO, "examples", e), t) for e in ON_EVERY_TARGET for t in OTHER_TARGETS]
        builds += [(cls.panic, None)]
        for path, target in builds:
            exe = os.path.join(bins, "prog")
            if os.path.exists(exe):
                os.remove(exe)
            args = ["build", path, "-o", exe] + (["--target", target] if target else [])
            result = cls._run(args)
            with open(exe, "rb") as fh:
                binary = fh.read()
            out[f"build {os.path.relpath(path, _REPO)} {target or 'x86_64-linux'}"] = (result, binary)
            if path == cls.panic:
                p = subprocess.run([exe], capture_output=True, text=True)
                out["panic native"] = (p.returncode, p.stdout, p.stderr.replace(cls.lib, "LIB"))
        out["panic run"] = cls._run(["run", cls.panic])
        for path in sorted(glob.glob(os.path.join(_REPO, "examples", "errors", "*.my"))):
            out[f"check {os.path.relpath(path, _REPO)}"] = cls._run(["check", path])
            with open(path, encoding="utf-8") as fh:
                if "runtime error" in fh.readline():
                    out[f"run {os.path.relpath(path, _REPO)}"] = cls._run(["run", path])
        return out

    def _same(self, prefix: str) -> None:
        keys = [k for k in self.carried if k.startswith(prefix)]
        self.assertTrue(keys)
        for k in keys:
            with self.subTest(k):
                self.assertEqual(self.carried[k], self.parsed[k])

    def test_the_programs_build_to_the_same_bytes(self):
        for k, (result, binary) in ((k, v) for k, v in self.carried.items() if k.startswith("build")):
            self.assertEqual(result[0], 0, f"{k}: {result[2]}")
            self.assertTrue(binary, k)
        self._same("build")

    def test_the_error_corpus_says_the_same(self):
        self._same("check examples/errors")
        self._same("run examples/errors")

    def test_an_error_in_a_body_read_late_is_at_its_place(self):
        code, out, err = self.carried["panic run"]
        self.assertEqual((code, out), (1, "1\n"))
        self.assertRegex(err, r"^runtime error: chunks: size 0 isn't positive\n  --> .*/std/list\.my:\d+:\d+\n")
        self._same("panic")


if __name__ == "__main__":
    unittest.main()
