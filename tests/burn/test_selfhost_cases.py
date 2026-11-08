"""The toolchain's own `#test` cases pass: every file of `selfhost/` and
`tools/` with cases, interpreted.

`test_selfhost_cli`'s corpus compares these files with the old Python
toolchain's recordings, and since every one of them has changed it skips them
all. So nothing ran their cases, and two went stale unnoticed
(`harness.my`'s `byte_offset`, MYLA-374; `lower.my`'s `map_lookup`, after
MYLA-313). The files run four at a time.
"""
from __future__ import annotations

import concurrent.futures
import glob
import os
import subprocess
import unittest

from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def _files() -> list[str]:
    files = sorted(glob.glob(os.path.join(_REPO, "selfhost", "*.my")))
    files += sorted(glob.glob(os.path.join(_REPO, "tools", "*", "*.my")))
    out = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            if any(line.lstrip().startswith("#test") for line in fh):
                out.append(path)
    return out


def _test(path: str) -> subprocess.CompletedProcess:
    return subprocess.run([selfhost_tool("main"), "test", path, "--stdlib", STDLIB_ROOT],
                          capture_output=True, text=True, timeout=900, cwd=_REPO)


class TestSelfhostCases(unittest.TestCase):
    def test_every_file_passes_its_cases(self):
        files = _files()
        self.assertGreater(len(files), 30)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_test, files))
        for path, proc in zip(files, results):
            with self.subTest(file=os.path.relpath(path, _REPO)):
                failed = [line for line in proc.stdout.splitlines() if line.startswith("FAIL")]
                self.assertEqual(proc.returncode, 0, "\n".join(failed) or proc.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
