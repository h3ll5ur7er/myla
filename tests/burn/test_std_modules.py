"""Every standard library module's own `#test` cases pass, interpreted and
natively (MYLA-325, D164).

The modules are found, not listed, so a new module of `lib/std/` is covered by
adding its cases. Left out: `std.rt`, the runtime itself, whose cases run in the
interpreter only (natively it is the code the harness runs on), and the other
targets' platform modules, which only their own targets can run.
"""
from __future__ import annotations

import glob
import os
import subprocess
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

NOT_NATIVE = {"rt"}
OTHER_TARGETS = {"platform_aarch64", "platform_wasm"}


def _modules() -> list[str]:
    """The names of the modules of `lib/std/` that have `#test` cases."""
    found = []
    for path in sorted(glob.glob(os.path.join(STDLIB_ROOT, "std", "*.my"))):
        name = os.path.basename(path)[:-3]
        if name in OTHER_TARGETS:
            continue
        with open(path, encoding="utf-8") as fh:
            if any(line.lstrip().startswith("#test") for line in fh):
                found.append(name)
    return found


def _test(name: str, *flags: str) -> subprocess.CompletedProcess:
    path = os.path.join(STDLIB_ROOT, "std", name + ".my")
    return subprocess.run([selfhost_tool("main"), "test", path, *flags, "--stdlib", STDLIB_ROOT],
                          capture_output=True, text=True, timeout=600)


class StdModuleCases(unittest.TestCase):
    def test_modules_are_found(self) -> None:
        names = _modules()
        for expected in ("json", "num", "fmt", "test"):
            self.assertIn(expected, names)

    def test_interpreted(self) -> None:
        for name in _modules():
            with self.subTest(module=name):
                proc = _test(name)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_native(self) -> None:
        for name in _modules():
            if name in NOT_NATIVE:
                continue
            with self.subTest(module=name):
                proc = _test(name, "--native")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
