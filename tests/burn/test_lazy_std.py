"""Burn test: the standard library's bodies read once called (D179, MYLA-432).

The lowering and the back ends call some functions of `std` by their mangled
names (`std$fmt$fmt_int` for an f-string's hole, `std$slice$take` for a
slice, the runtime's), where no code the checker checks calls them. The
checker marks those on `backend_std_functions` (`selfhost/checker.my`) as
called, so that a body the loader left unread is always read for them, and a
build that asks for another function of `std` nobody called is an internal
error (`Checker.unmarked_std`). The list is checked here against the names
the back ends' sources write.

An imported module's bodies are read so (MYLA-413), a program's own modules
whole; a body read late has the eager check's error at its place.

What is built must not depend on which bodies were read (MYLA-552): with
MYLA_EAGER_BODIES=1 the loader reads every body it left for later before the
check (`eager_bodies`), and the parity programs and the compiler build to the
same assembly, on x86-64 and aarch64, as when only the called ones are read.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from ._native import CAN_BUILD_NATIVE
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_SELFHOST = os.path.join(_REPO, "selfhost")

# the lowering, the back ends and what they share: the files that may name a
# function of `std` to call
BACK_END_FILES = ["lower.my", "codegen.my", "ir.my", "ir_util.my", "ir_x86.my", "ir_a64.my", "ir_wasm.my",
                  "runtime_x86.my", "runtime_a64.my", "runtime_wasm.my", "inline.my", "ownership.my",
                  "anf.my", "hoist.my", "ranges.my", "ssa.my", "dwarf.my"]


def listed_names() -> set[str]:
    """The names of `backend_std_functions` in `selfhost/checker.my`."""
    with open(os.path.join(_SELFHOST, "checker.my"), encoding="utf-8") as fh:
        src = fh.read()
    start = src.index("pub fun backend_std_functions() -> [str] {")
    body = src[start:src.index("\n}\n", start)]
    return set(re.findall(r'"(std\$[a-z_0-9]+\$[A-Za-z_][A-Za-z_0-9]*)"', body))


def named_by(path: str) -> dict[str, int]:
    """The functions of `std` the file `path` names (outside its comments and
    `#test` cases), each with the first line that does: a mangled name in a
    string (`"std$rt$alloc"`, `"bl myla_std$rt$fmod"`) or std.platform's by
    `platform_fn("…")`."""
    out: dict[str, int] = {}
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            text = line.strip()
            if text.startswith("//") or text.startswith("#test"):
                continue
            for s in re.findall(r'"[^"\n]*"', line):
                for name in re.findall(r"std\$[a-z_0-9]+\$[A-Za-z_][A-Za-z_0-9]*", s):
                    out.setdefault(name, n)
            for name in re.findall(r'platform_fn\("([a-z_0-9]+)"\)', line):
                out.setdefault("std$platform$" + name, n)
    return out


class BackEndNames(unittest.TestCase):
    def test_every_name_a_back_end_writes_is_listed(self) -> None:
        listed = listed_names()
        self.assertGreater(len(listed), 50)
        missing = []
        seen: set[str] = set()
        for f in BACK_END_FILES:
            for name, line in named_by(os.path.join(_SELFHOST, f)).items():
                seen.add(name)
                if name not in listed:
                    missing.append(f"selfhost/{f}:{line}: {name}")
        self.assertEqual(missing, [], "add these to backend_std_functions in selfhost/checker.my")
        # and nothing on the list that no back end names any more
        self.assertEqual(sorted(listed - seen), [])

    def test_the_scan_finds_a_name(self) -> None:
        # the scan itself: a name in a string, not one in a comment or a case
        path = os.path.join(_SELFHOST, "lower.my")
        names = named_by(path)
        self.assertIn("std$fmt$fmt_int", names)
        self.assertIn("std$slice$take", names)
        self.assertNotIn("std$list$sum", names)  # only in a `#test` case of `checked_code`


class ImportedStdBodies(unittest.TestCase):
    """MYLA-413, D179 (2): an imported module of `std` has its functions'
    bodies read once called, with the error of one read at the place and in
    the words of the eager check (the module's own `myla check`); a
    program's own modules are read whole (D179 (3))."""

    # a type error, a function that calls it, and (in a library of its own,
    # as a parse error stops the eager check of the module) a parse error
    BROKEN = ("\npub fun broken_413() -> int {\n    return \"no\"\n}\n\n"
              "pub fun calls_broken_413() -> int {\n    return broken_413()\n}\n")
    GARBLED = "\npub fun garbled_413() -> int {\n    let = 1\n    return 2\n}\n"

    @classmethod
    def setUpClass(cls) -> None:
        cls.myla = selfhost_tool("main")
        cls._tmp = tempfile.TemporaryDirectory(prefix="myla_lazy_std_")
        cls.work = cls._tmp.name
        cls.lib = os.path.join(cls.work, "lib")
        cls.plib = os.path.join(cls.work, "plib")
        for lib, text in ((cls.lib, cls.BROKEN), (cls.plib, cls.GARBLED)):
            shutil.copytree(STDLIB_ROOT, lib)
            with open(os.path.join(lib, "std", "text.my"), "a", encoding="utf-8") as fh:
                fh.write(text)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def myla_cmd(self, *argv: str, lib: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([self.myla, *argv, "--stdlib", lib or self.lib], cwd=self.work,
                              capture_output=True, text=True, timeout=600)

    def write(self, name: str, text: str) -> str:
        path = os.path.join(self.work, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def calling(self, call: str) -> str:
        return self.write("calls.my", f"import std.text as text\n\nfun main() {{\n    print({call})\n}}\n")

    def test_a_body_nobody_calls_is_not_read(self) -> None:
        for lib in (self.lib, self.plib):
            path = self.calling('text.fill("a b c", 3)')
            for cmd in ("check", "run"):
                proc = self.myla_cmd(cmd, path, lib=lib)
                self.assertEqual((proc.stderr, proc.returncode), ("", 0), (cmd, lib))
            if CAN_BUILD_NATIVE:
                exe = os.path.join(self.work, "uncalled")
                proc = self.myla_cmd("build", path, "-o", exe, lib=lib)
                self.assertEqual((proc.stderr, proc.returncode), ("", 0))
                self.assertEqual(subprocess.run([exe], capture_output=True, text=True).stdout, "a b\nc\n")

    def test_a_called_body_has_the_eager_error(self) -> None:
        # the module checked on its own reads every body; called, the body
        # read late gives the same error, place and source line
        eager = self.myla_cmd("check", os.path.join(self.lib, "std", "text.my"))
        self.assertEqual(eager.returncode, 1)
        first = eager.stderr.split("\n")[:5]
        self.assertEqual(first[0], "type error: return type mismatch: expected 'int32', found 'str'", eager.stderr)
        for call in ("text.broken_413()", "text.calls_broken_413()"):
            proc = self.myla_cmd("check", self.calling(call))
            self.assertEqual(proc.returncode, 1, call)
            self.assertEqual(proc.stderr.split("\n")[:5], first, call)

    def test_a_called_body_has_the_eager_parse_error(self) -> None:
        eager = self.myla_cmd("check", os.path.join(self.plib, "std", "text.my"), lib=self.plib)
        self.assertEqual(eager.returncode, 1)
        first = eager.stderr.split("\n")[:5]
        self.assertEqual(first[0], "parse error: expected variable name, found '='", eager.stderr)
        proc = self.myla_cmd("check", self.calling("text.garbled_413()"), lib=self.plib)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr.split("\n")[:5], first)

    def test_a_programs_own_module_is_read_whole(self) -> None:
        # D179 (3): `myla check` means every function of the program's own
        # modules checks, called or not
        os.makedirs(os.path.join(self.work, "own"), exist_ok=True)
        self.write("own/helper.my", "pub fun used() -> int {\n    return 1\n}\n\npub fun unused() -> int {\n    return \"no\"\n}\n")
        path = self.write("own/main.my", "from .helper import used\n\nfun main() {\n    print(used())\n}\n")
        proc = self.myla_cmd("check", path)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("type error: return type mismatch", proc.stderr)
        self.assertIn("helper.my:6:", proc.stderr)

    def test_a_programs_own_std_directory_is_read_whole(self) -> None:
        # MYLA-413 (C4 of the review of 2026-11-12): laziness goes by the
        # file's root, not by a module id that starts `std$`: a program's own
        # `std/helper.my` is read whole, its type error and its parse error
        # reported as those of `other/helper.my` are
        bad_type = "pub fun ok() -> int {\n    return 1\n}\n\npub fun broken() -> int {\n    return \"no\"\n}\n"
        bad_parse = "pub fun ok() -> int {\n    return 1\n}\n\npub fun garbled() -> int {\n    let = 1\n    return 2\n}\n"
        for text, want in ((bad_type, "type error: return type mismatch"), (bad_parse, "parse error: expected variable name")):
            for d in ("std", "other"):
                with self.subTest(dir=d, want=want):
                    root = os.path.join(self.work, "own_" + d)
                    os.makedirs(os.path.join(root, d), exist_ok=True)
                    self.write(f"own_{d}/{d}/helper.my", text)
                    path = self.write(f"own_{d}/main.my", f"from .{d}.helper import ok\n\nfun main() {{\n    print(ok())\n}}\n")
                    for cmd in ("check", "run"):
                        proc = self.myla_cmd(cmd, path)
                        self.assertEqual(proc.returncode, 1, (cmd, proc.stdout))
                        self.assertTrue(proc.stderr.startswith(want), proc.stderr)
                        self.assertIn(f"{d}/helper.my:", proc.stderr)


class EagerOracle(unittest.TestCase):
    """MYLA-552: the parity programs and the compiler build to the same
    assembly with every body read (MYLA_EAGER_BODIES=1) as with those read
    once called. The owned parameters' vote (`find_kept_params`) counted the
    calls in every body loaded, so a body read changed how others were
    built (`packed_byte_lists` did, with output equal)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.gen = selfhost_tool("gen_main")
        cls._tmp = tempfile.TemporaryDirectory(prefix="myla_eager_")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def assembly(self, path: str, target: str, eager: bool) -> str:
        env = dict(os.environ, MYLA_EAGER_BODIES="1" if eager else "")
        proc = subprocess.run([self.gen, path, STDLIB_ROOT, "--target", target], capture_output=True, text=True,
                              cwd=_REPO, env=env, timeout=600)
        self.assertEqual(proc.returncode, 0, f"{path} {target} eager={eager}: {proc.stderr[-2000:]}")
        return proc.stdout

    def differing(self, paths: list[str], target: str) -> list[str]:
        def one(path: str) -> str:
            return "" if self.assembly(path, target, False) == self.assembly(path, target, True) else path
        with ThreadPoolExecutor(max(1, min(4, os.cpu_count() or 1))) as pool:
            return [os.path.basename(p) for p in pool.map(one, paths) if p]

    def parity_programs(self) -> list[str]:
        from .test_compiler_parity import PROGRAMS
        out = []
        for name, src in PROGRAMS.items():
            path = os.path.join(self._tmp.name, name + ".my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)
            out.append(path)
        return out

    def test_the_parity_programs_build_the_same(self) -> None:
        paths = self.parity_programs()
        self.assertGreater(len(paths), 100)
        for target in ("x86_64-linux", "aarch64-linux"):
            with self.subTest(target=target):
                self.assertEqual(self.differing(paths, target), [])

    def test_the_compiler_builds_the_same(self) -> None:
        self.assertEqual(self.differing([os.path.join(_SELFHOST, "main.my")], "x86_64-linux"), [])


if __name__ == "__main__":
    unittest.main()
