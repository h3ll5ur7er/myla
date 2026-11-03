"""Burn test: the benchmarks are correct (MYLA-242).

Each benchmark under benchmarks/ (`benchmarks/run.py` measures them) runs at
its small `test_size`: the interpreter, native code and both C versions
(idiomatic, and with Myla's semantics) print the same, and its `#test` cases
pass. So the set can't drift into measuring wrong programs."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import _REPO, selfhost_tool

_BENCH = os.path.join(_REPO, "benchmarks")


def _names() -> list[str]:
    return sorted(d for d in os.listdir(_BENCH) if os.path.isfile(os.path.join(_BENCH, d, "bench.json")))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Benchmarks(unittest.TestCase):
    def test_there_are_benchmarks(self):
        self.assertGreaterEqual(len(_names()), 3)

    def test_every_version_prints_the_same(self):
        myla = selfhost_tool("main")
        cc = shutil.which("cc") or shutil.which("gcc")
        with tempfile.TemporaryDirectory() as tmp:
            for name in _names():
                with self.subTest(benchmark=name):
                    with open(os.path.join(_BENCH, name, "bench.json"), encoding="utf-8") as fh:
                        size = str(json.load(fh)["test_size"])
                    src = os.path.join(_BENCH, name, name + ".my")
                    ran = subprocess.run([myla, "run", src, size], capture_output=True, text=True)
                    self.assertEqual(ran.returncode, 0, ran.stderr)
                    want = ran.stdout
                    exe = os.path.join(tmp, name)
                    built = subprocess.run([myla, "build", src, "-o", exe], capture_output=True, text=True)
                    self.assertEqual(built.returncode, 0, built.stderr)
                    self.assertEqual(subprocess.run([exe, size], capture_output=True, text=True).stdout, want)
                    tested = subprocess.run([myla, "test", src], capture_output=True, text=True)
                    self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
                    if cc is None:
                        continue
                    for c_file in (name + ".c", name + "_myla.c"):
                        c_exe = os.path.join(tmp, c_file + ".out")
                        compiled = subprocess.run([cc, "-O1", "-fwrapv", "-Wall", "-Werror", "-o", c_exe,
                                                   os.path.join(_BENCH, name, c_file)], capture_output=True, text=True)
                        self.assertEqual(compiled.returncode, 0, compiled.stderr)
                        out = subprocess.run([c_exe, size], capture_output=True, text=True).stdout
                        self.assertEqual(out, want, c_file)


if __name__ == "__main__":
    unittest.main()
