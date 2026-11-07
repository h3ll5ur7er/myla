"""Burn test: the embedded standard library is current (MYLA-243).

`selfhost/embedded_std.my` is generated from `lib/` by `tools/embed/main.my`,
which `scripts/bootstrap.sh` runs; it is committed, so a change to `lib/`
without a bootstrap would leave the toolchain carrying an older library. The
tool's `--check` mode says whether the module is what `lib/` gives, and
notices a change."""
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import _REPO, STDLIB_ROOT, myla_tool

_MODULE = os.path.join(_REPO, "selfhost", "embedded_std.my")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class EmbeddedStd(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.embed = myla_tool("tools/embed/main.my", "embed")

    def test_the_module_is_what_lib_gives(self):
        proc = subprocess.run([self.embed, STDLIB_ROOT, _MODULE, "--check"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr + " (run scripts/bootstrap.sh)")

    def test_a_change_to_lib_is_noticed_and_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib = os.path.join(tmp, "lib")
            shutil.copytree(STDLIB_ROOT, lib)
            module = os.path.join(tmp, "embedded_std.my")
            shutil.copy(_MODULE, module)
            with open(os.path.join(lib, "std", "io.my"), "a", encoding="utf-8") as fh:
                fh.write("// a change\n")
            checked = subprocess.run([self.embed, lib, module, "--check"], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 1)
            self.assertIn("run scripts/bootstrap.sh", checked.stderr)
            written = subprocess.run([self.embed, lib, module], capture_output=True, text=True)
            self.assertEqual((written.returncode, written.stdout), (0, f"embed: wrote {module}\n"))
            with open(module, encoding="utf-8") as fh:
                self.assertIn("// a change\\n", fh.read())
            again = subprocess.run([self.embed, lib, module], capture_output=True, text=True)
            self.assertEqual((again.returncode, again.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class StdlibRoot(unittest.TestCase):
    def test_a_root_that_is_not_there_says_so(self):
        # a std import under a root named by MYLA_STDLIB or --stdlib that
        # doesn't exist says which, not only that it can't resolve (the
        # review of 2026-11-06)
        from tests.burn._tools import selfhost_tool
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "j.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("import std.json as json\n\nfun main() {\n    print(1)\n}\n")
            missing = os.path.join(tmp, "no-such-lib")
            want = (f"cannot resolve import 'std.json': the standard library root '{missing}' "
                    "(from --stdlib or MYLA_STDLIB) is not a directory")
            for args, env in ((["--stdlib", missing], {}), ([], {"MYLA_STDLIB": missing})):
                with self.subTest(args=args, env=env):
                    p = subprocess.run([selfhost_tool("main"), "run", path, *args], capture_output=True, text=True,
                                       env=dict(os.environ, **env))
                    self.assertEqual(p.returncode, 1, p.stderr)
                    self.assertIn(want, p.stderr)
            # the embedded library, as without either
            env = {k: v for k, v in os.environ.items() if k != "MYLA_STDLIB"}
            p = subprocess.run([selfhost_tool("main"), "run", path], capture_output=True, text=True, env=env)
            self.assertEqual((p.stdout, p.returncode), ("1\n", 0), p.stderr)
