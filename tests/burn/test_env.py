"""Burn test: environment variables (`std.process.env`, MYLA-243).

`env(name)` is `Some` of the variable's value, `""` included, or `None` when
the environment has no variable of that name (a longer or shorter name that
shares a prefix doesn't count). The self-hosted interpreter and native code
agree."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """from std.process import env

fun show(name: str) {
    match env(name) {
        Some(v) => print(f"{name}=[{v}]"),
        None => print(f"{name} unset"),
    }
}

fun main() {
    show("MYLA_TEST_VAR")
    show("MYLA_TEST_EMPTY")
    show("MYLA_TEST")
    show("MYLA_TEST_VAR_LONGER")
    show("MYLA_TEST_UNSET")
    show("")
}
"""

_WANT = ("MYLA_TEST_VAR=[a=b c]\nMYLA_TEST_EMPTY=[]\nMYLA_TEST unset\nMYLA_TEST_VAR_LONGER unset\n"
         "MYLA_TEST_UNSET unset\n unset\n")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Env(unittest.TestCase):
    def test_in_the_interpreter_and_natively(self):
        myla = selfhost_tool("main")
        environment = {k: v for k, v in os.environ.items() if not k.startswith("MYLA_TEST")}
        environment.update({"MYLA_TEST_VAR": "a=b c", "MYLA_TEST_EMPTY": ""})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "env.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_PROGRAM)
            proc = subprocess.run([myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True,
                                  env=environment)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))
            exe = os.path.join(tmp, "env")
            built = subprocess.run([myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], capture_output=True,
                                   text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            proc = subprocess.run([exe], capture_output=True, text=True, env=environment)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))


if __name__ == "__main__":
    unittest.main()
