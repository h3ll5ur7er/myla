"""Every standard library module's own `#test` cases pass, interpreted and
natively (MYLA-325, D164), and on the target MYLA_TEST_TARGET names
(`scripts/test-target.py`): on wasm32 under Node, where `myla test` runs the
harness again after each case that ends a run (MYLA-370); under qemu-aarch64
it is excused (`_targets.py`: a qemu process per case takes minutes).

The modules are found, not listed, so a new module of `lib/std/` is covered by
adding its cases, and each run must report every case of the file (one per
`#test` line), all passed. Left out natively: `std.rt`, the runtime itself,
whose cases run in the interpreter only (natively it is the code the harness
runs on), and the other targets' platform modules, which only their own
targets can run: on a target, its own platform module runs (`platform_wasm`
on wasm32, `platform_aarch64` on aarch64), which is its `std.platform`, built
as that module (MYLA-397). Interpreted, all three platform modules run
(MYLA-418: the 36 cases of the foreign two ran nowhere, MYLA-325).
"""
from __future__ import annotations

import glob
import os
import subprocess
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, TEST_TARGET, target_flags
from ._tools import STDLIB_ROOT, selfhost_tool

NOT_NATIVE = {"rt"}
PLATFORMS = {"platform", "platform_aarch64", "platform_wasm"}   # `platform` is the host's (D161)
OWN_PLATFORM = {"": "platform", "aarch64-linux": "platform_aarch64", "wasm32-wasi": "platform_wasm"}
_RUN_MJS = os.path.join(os.path.dirname(STDLIB_ROOT), "tools", "wasm", "run.mjs")


def _modules(target: str | None = "") -> list[str]:
    """The names of the modules of `lib/std/` that have `#test` cases, with
    the platform module of `target` ("" the host's) and no other; with
    `target` None, every platform module."""
    return [name for name in sorted(_COUNTS)
            if target is None or name not in PLATFORMS or name == OWN_PLATFORM.get(target)]


def _case_counts() -> dict[str, int]:
    """Each module of `lib/std/` with cases, and how many: one per `#test`
    attribute, each on a line of its own."""
    counts = {}
    for path in sorted(glob.glob(os.path.join(STDLIB_ROOT, "std", "*.my"))):
        with open(path, encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.lstrip().startswith("#test"))
        if n > 0:
            counts[os.path.basename(path)[:-3]] = n
    return counts


_COUNTS = _case_counts()


def _test(name: str, *flags: str) -> subprocess.CompletedProcess:
    path = os.path.join(STDLIB_ROOT, "std", name + ".my")
    env = dict(os.environ)
    if TEST_TARGET == "wasm32-wasi":
        env["MYLA_EMULATOR"] = f"node {_RUN_MJS}"
    return subprocess.run([selfhost_tool("main"), "test", path, *flags, "--stdlib", STDLIB_ROOT],
                          capture_output=True, text=True, timeout=600, env=env)


class StdModuleCases(unittest.TestCase):
    def test_modules_are_found(self) -> None:
        names = _modules()
        for expected in ("json", "num", "fmt", "test"):
            self.assertIn(expected, names)
        # each target's own platform module, and only that one (MYLA-397)
        self.assertIn("platform_wasm", _modules("wasm32-wasi"))
        self.assertNotIn("platform", _modules("wasm32-wasi"))
        self.assertIn("platform_aarch64", _modules("aarch64-linux"))
        self.assertNotIn("platform_wasm", _modules("aarch64-linux"))

        self.assertEqual(len(_modules(None)), len(_modules()) + 2)

    def _passes_all(self, proc: subprocess.CompletedProcess, name: str) -> None:
        n = _COUNTS[name]
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(proc.stdout.endswith(f"\n{n}/{n} passed.\n"), proc.stdout[-2000:])

    def test_interpreted(self) -> None:
        # the platform modules of the other targets too: the interpreter
        # runs their cases on this machine (MYLA-325)
        for name in _modules(None):
            with self.subTest(module=name):
                self._passes_all(_test(name), name)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_native(self) -> None:
        # on the target MYLA_TEST_TARGET names, the native report is the
        # host's, every case run (on wasm32 too, MYLA-370)
        flags = target_flags() or ["--native"]
        for name in _modules(TEST_TARGET):
            if name in NOT_NATIVE:
                continue
            with self.subTest(module=name):
                self._passes_all(_test(name, *flags), name)


class RootSpellings(unittest.TestCase):
    """A module of `lib/std` tested or checked with its library's root, or
    the file, written with a leading `..` (MYLA-545, MYLA-397): it is that
    library's module, not the entry of a program with the library beside it
    (`duplicate method 'map'`)."""

    def _run(self, cwd: str, *argv: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "MYLA_STDLIB"}
        return subprocess.run([selfhost_tool("main"), *argv], capture_output=True, text=True,
                              timeout=600, cwd=cwd, env=env)

    def test_a_root_or_a_file_written_with_dot_dot(self) -> None:
        std = os.path.join(STDLIB_ROOT, "std")
        repo = os.path.dirname(STDLIB_ROOT)
        up = os.path.join(os.pardir, os.path.basename(repo), "lib", "std", "option.my")
        lib_up = os.path.join(os.pardir, os.pardir, os.path.basename(STDLIB_ROOT))
        for cwd, name, argv in ((std, "option", ["test", "option.my", "--stdlib", ".."]),
                                (std, "yaml", ["test", "yaml.my", "--stdlib", lib_up]),
                                (repo, "option", ["test", up, "--stdlib", "lib"])):
            with self.subTest(argv=argv):
                proc = self._run(cwd, *argv)
                n = _COUNTS[name]
                self.assertEqual(proc.stderr, "")
                self.assertTrue(proc.stdout.endswith(f"\n{n}/{n} passed.\n"), proc.stdout[-2000:])
        proc = self._run(std, "check", "fs.my", "--stdlib", "..")
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("ok\n", "", 0))


if __name__ == "__main__":
    unittest.main()
