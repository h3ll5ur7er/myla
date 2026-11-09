"""`myla test` runs the file's own cases, not an imported module's (MYLA-360).

A method on a built-in type is named `str.bang` in every module, so the
runners took the cases of an imported module's `impl str` for the entry
file's: the interpreter ran them, and the native harness copied their
arguments by byte spans out of the entry file's text and didn't build. The
loader now keeps the cases of the file being tested only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

_UTIL = """\
impl str {
    #test("a")["a!"]
    #test("b")["b!"]
    fun bang(self) -> str {
        return self + "!"
    }
}

#test(1)[2]
pub fun inc(n: int) -> int {
    return n + 1
}
"""

_MAIN = """\
from .util import inc

#test("x")["x!!"]
fun twice(s: str) -> str {
    return s.bang().bang()
}

#test(4)[6]
fun plus_two(n: int) -> int {
    return inc(inc(n))
}
"""

# a module of the standard library that imports the method modules
# explicitly, as the modules of `std` must (D164)
_STD_MODULE = """\
import std.str as str_m
import std.list as list_m
import std.hash as hash_m
import std.char as char_m

#test("a,b")[2]
fun parts(s: str) -> int {
    return s.split(",").len()
}
"""


def _test(path: str, stdlib: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run([selfhost_tool("main"), "test", path, *flags, "--stdlib", stdlib],
                          capture_output=True, text=True, timeout=600)


class TestImportedCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, rel: str, text: str) -> str:
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_a_user_module_brings_no_cases(self):
        self.write("util.my", _UTIL)
        main = self.write("main.my", _MAIN)
        proc = _test(main, STDLIB_ROOT)
        self.assertEqual(proc.stdout, "PASS  twice #1\nPASS  plus_two #1\n\n2/2 passed.\n", proc.stderr)
        self.assertEqual(proc.returncode, 0)
        # the module's own cases still run when it is the file tested
        proc = _test(os.path.join(self.tmp, "util.my"), STDLIB_ROOT)
        self.assertIn("3/3 passed.", proc.stdout, proc.stderr)

    def test_an_imported_module_s_cases_are_not_parsed(self):
        # only the entry's cases are parsed: an imported module's are
        # skipped unparsed (MYLA-396), unlexed too (MYLA-359), so std.int's
        # thousands cost an importer nothing and a broken case shows only
        # when its own file is tested
        self.write("broken.my", "#test(1 +)[2]\npub fun one() -> int {\n    return 1\n}\n\n"
                                "#test(\"@\", 1 @ 2)[f\"{\")\"}\"] // a name\nfun two(s: str, n: int) -> int {\n    return 2\n}\n")
        main = self.write("main.my", "from .broken import one\n\n#test()[1]\nfun f() -> int {\n    return one()\n}\n")
        proc = _test(main, STDLIB_ROOT)
        self.assertEqual(proc.stdout, "PASS  f #1\n\n1/1 passed.\n", proc.stderr)
        self.assertEqual(proc.returncode, 0)
        proc = _test(os.path.join(self.tmp, "broken.my"), STDLIB_ROOT)
        self.assertIn("lex error: unexpected character '@'", proc.stdout + proc.stderr)
        self.assertNotEqual(proc.returncode, 0)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_a_user_module_brings_no_cases_natively(self):
        self.write("util.my", _UTIL)
        main = self.write("main.my", _MAIN)
        proc = _test(main, STDLIB_ROOT, "--native")
        self.assertEqual(proc.stderr, "")
        self.assertEqual(proc.stdout, "PASS  twice #1\nPASS  plus_two #1\n\n2/2 passed.\n")

    def std_copy(self) -> str:
        root = os.path.join(self.tmp, "lib")
        shutil.copytree(STDLIB_ROOT, root)
        self.write(os.path.join("lib", "std", "zz.my"), _STD_MODULE)
        return root

    def test_a_std_module_importing_the_method_modules(self):
        root = self.std_copy()
        proc = _test(os.path.join(root, "std", "zz.my"), root)
        self.assertEqual(proc.stdout, "PASS  parts #1\n\n1/1 passed.\n", proc.stderr)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_a_std_module_importing_the_method_modules_natively(self):
        root = self.std_copy()
        proc = _test(os.path.join(root, "std", "zz.my"), root, "--native")
        self.assertEqual(proc.stderr, "")
        self.assertEqual(proc.stdout, "PASS  parts #1\n\n1/1 passed.\n")


if __name__ == "__main__":
    unittest.main()
