"""Every standard library module's own `#test` cases pass, interpreted and
natively (MYLA-325, D164), and on the target MYLA_TEST_TARGET names
(`scripts/test-target.py`): on wasm32 under Node, where `myla test` runs the
harness again after each case that ends a run (MYLA-370); under qemu-aarch64
it is excused (`_targets.py`: a qemu process per case takes minutes).

The modules are found, not listed, so a new module of `lib/std/` is covered by
adding its cases. Left out: `std.rt`, the runtime itself, whose cases run in the
interpreter only (natively it is the code the harness runs on), and the other
targets' platform modules, which only their own targets can run: on a target,
its own platform module runs (`platform_wasm` on wasm32, `platform_aarch64` on
aarch64), which is its `std.platform`, built as that module (MYLA-397).
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


def _modules(target: str = "") -> list[str]:
    """The names of the modules of `lib/std/` that have `#test` cases, with
    the platform module of `target` ("" the host's) and no other."""
    found = []
    for path in sorted(glob.glob(os.path.join(STDLIB_ROOT, "std", "*.my"))):
        name = os.path.basename(path)[:-3]
        if name in PLATFORMS and name != OWN_PLATFORM.get(target):
            continue
        with open(path, encoding="utf-8") as fh:
            if any(line.lstrip().startswith("#test") for line in fh):
                found.append(name)
    return found


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

    def test_interpreted(self) -> None:
        for name in _modules():
            with self.subTest(module=name):
                proc = _test(name)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_native(self) -> None:
        # on the target MYLA_TEST_TARGET names, the native report is the
        # host's, every case run (on wasm32 too, MYLA-370)
        flags = target_flags() or ["--native"]
        for name in _modules(TEST_TARGET):
            if name in NOT_NATIVE:
                continue
            with self.subTest(module=name):
                proc = _test(name, *flags)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn(" passed.", proc.stdout)


if __name__ == "__main__":
    unittest.main()
