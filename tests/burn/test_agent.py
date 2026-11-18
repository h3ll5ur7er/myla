"""Burn test: the agent harness example, `examples/agent/` (MYLA-758).

A project, so the example suites (which run the files of `examples/`) don't
see it: its `#test` cases run here (among them the offline demo end to end,
streamed and not, and a compaction against the stand-in for the server),
and so does `--demo` through the command line.
"""
import os
import subprocess
import unittest

from tests.burn._tools import STDLIB_ROOT, selfhost_tool

AGENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "examples", "agent")
)


def _myla(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([selfhost_tool("main"), *args, "--stdlib", STDLIB_ROOT],
                          capture_output=True, text=True, cwd=AGENT_DIR, timeout=300)


class TestAgent(unittest.TestCase):
    def test_cases_pass(self):
        proc = _myla("test")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertRegex(proc.stdout, r"\n(\d+)/\1 passed in 12 files\.\n")

    def test_demo(self):
        proc = _myla("run", "--demo")
        self.assertEqual((proc.stderr, proc.returncode), ("", 0))
        self.assertIn("summary.md:\n# Summary\n\n- Teach the toaster to compile.\n- Buy a towel.\n", proc.stdout)
        self.assertIn("model: Done: summary.md has the first line of each note (wrote 58 bytes).\n", proc.stdout)
        self.assertIn("4 requests", proc.stdout)


if __name__ == "__main__":
    unittest.main()
