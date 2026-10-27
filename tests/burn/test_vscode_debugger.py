"""Burn test: the VS Code extension's debug adapter against real gdb (MYLA-99).

Runs `vscode-extension/myla/test/integration/adapter.test.ts` under node (types
stripped, no `npm ci` needed): the adapter on stdio builds Myla programs with
`myla build -g` and debugs them with gdb (breakpoints, stepping, the stack,
variables, evaluation, runtime errors, pause, exit codes, build errors). Once
with the Python CLI and once with the self-hosted CLI, so the debug
information of both backends works in the adapter. Skipped without gdb or
node 22.6+.
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
_EXTENSION = os.path.join(_REPO, "vscode-extension", "myla")


def _node_strips_types() -> bool:
    if shutil.which("node") is None:
        return False
    return subprocess.run(["node", "--experimental-strip-types", "-e", "0"], capture_output=True).returncode == 0


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(shutil.which("gdb"), "needs gdb")
@unittest.skipUnless(_node_strips_types(), "needs node 22.6+")
class TestDebugAdapter(unittest.TestCase):
    def run_adapter_tests(self, cli: str) -> None:
        env = dict(os.environ, MYLA_CLI=cli)
        env.pop("MYLA_DAP_BUNDLE", None)
        proc = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings", "--test",
             os.path.join("test", "integration", "adapter.test.ts")],
            cwd=_EXTENSION, env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout[-6000:] + proc.stderr[-2000:])
        self.assertIn("# fail 0", proc.stdout)
        self.assertIn("# skipped 0", proc.stdout)

    def test_with_the_python_cli(self) -> None:
        self.run_adapter_tests(os.path.join(_REPO, "myla.py"))

    def test_with_the_self_hosted_cli(self) -> None:
        # the CLI in a checkout's layout, so it finds the standard library
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "build"))
            os.makedirs(os.path.join(root, "src"))
            os.symlink(os.path.join(_REPO, "src", "myla"), os.path.join(root, "src", "myla"))
            cli = os.path.join(root, "build", "myla")
            shutil.copy(selfhost_tool("main"), cli)
            self.run_adapter_tests(cli)


if __name__ == "__main__":
    unittest.main()
