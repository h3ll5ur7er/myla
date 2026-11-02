"""The programs the Python toolchain's unit tests ran (MYLA-219).

Before the Python toolchain was retired, `scripts/harvest_unit_programs.py`
kept every single-module program its unit tests ran through the interpreter,
with what came out: what it printed, and its exit status or runtime error
(`tests/burn/data/unit_programs.json`). Each one now runs in the self-hosted
interpreter (`myla run`) and as a native binary, and must give the same
output and exit status, and the interpreter the same runtime error (natively
some runtime errors are worded more shortly). Native runs use one worker, as
the interpreter runs tasks one at a time."""
import json
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA = os.path.join(_REPO, "tests", "burn", "data", "unit_programs.json")


def _programs() -> list[dict]:
    with open(_DATA, encoding="utf-8") as fh:
        return json.load(fh)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestUnitPrograms(unittest.TestCase):
    def check(self, interpreted: bool) -> None:
        myla = selfhost_tool("main")
        programs = _programs()
        self.assertGreater(len(programs), 90)
        with tempfile.TemporaryDirectory() as tmp:
            for n, prog in enumerate(programs):
                with self.subTest(program=n, source=prog["source"][:80]):
                    path = os.path.join(tmp, f"p{n}.my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(prog["source"])
                    args = prog["argv"][1:] if prog["argv"] else []
                    if interpreted:
                        proc = subprocess.run([myla, "run", path, *args, "--stdlib", STDLIB_ROOT],
                                              capture_output=True, text=True, timeout=60)
                    else:
                        binary = os.path.join(tmp, f"p{n}")
                        built = subprocess.run([myla, "build", path, "-o", binary, "--stdlib", STDLIB_ROOT],
                                               capture_output=True, text=True, timeout=120)
                        self.assertEqual(built.returncode, 0, built.stderr)
                        proc = subprocess.run([binary, *args], capture_output=True, text=True, timeout=60,
                                              env={**os.environ, "MYLA_THREADS": "1"})
                    self.assertEqual(proc.stdout, prog["stdout"])
                    if "runtime_error" in prog:
                        self.assertNotEqual(proc.returncode, 0)
                        # natively some errors have shorter messages (the error
                        # corpus's `native` directives): the wording is the
                        # interpreter's to match
                        expected = f"runtime error: {prog['runtime_error']}" if interpreted else "runtime error: "
                        self.assertIn(expected, proc.stderr)
                    else:
                        self.assertEqual(proc.returncode, prog["exit"], proc.stderr)

    def test_in_the_self_hosted_interpreter(self) -> None:
        self.check(interpreted=True)

    def test_natively(self) -> None:
        self.check(interpreted=False)


if __name__ == "__main__":
    unittest.main()
