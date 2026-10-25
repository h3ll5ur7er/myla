"""Burn tests: `myla build -g` produces a DWARF line table that real tools read
(MYLA-71). readelf (binutils) is always there when native builds work; the gdb
test runs only where gdb is installed."""
import os
import shutil
import subprocess
import tempfile
import unittest

from myla.cli import main as myla
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON

PROGRAM = (
    "fun add(a: int, b: int) -> int {\n"   # line 1
    "    let c = a + b\n"                   # line 2
    "    return c\n"                        # line 3
    "}\n"
    "\n"
    "fun main() {\n"                        # line 6
    "    print(add(2, 3))\n"                # line 7
    "}\n"
)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestLineTables(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.realpath(tmp.name)
        self.source = os.path.join(self.dir, "prog.my")
        with open(self.source, "w", encoding="utf-8") as fh:
            fh.write(PROGRAM)

    def build(self, *flags: str) -> str:
        binary = os.path.join(self.dir, "prog" + "".join(flags).replace("-", "_"))
        self.assertEqual(myla(["build", self.source, "-o", binary, *flags]), 0)
        return binary

    def test_readelf_sees_myla_source_lines(self):
        dump = subprocess.run(
            ["readelf", "--debug-dump=decodedline", self.build("-g")],
            capture_output=True, text=True, check=True,
        ).stdout
        rows = {tuple(line.split()[:2]) for line in dump.splitlines()
                if line.startswith("prog.my")}
        for line in ("1", "2", "3", "6", "7"):
            self.assertIn(("prog.my", line), rows)

    def test_line_tables_do_not_change_behaviour(self):
        plain = subprocess.run([self.build()], capture_output=True, text=True)
        debug = subprocess.run([self.build("-g")], capture_output=True, text=True)
        self.assertEqual((plain.stdout, plain.returncode), ("5\n", 0))
        self.assertEqual((debug.stdout, debug.returncode), (plain.stdout, plain.returncode))

    @unittest.skipUnless(shutil.which("gdb"), "gdb is not installed")
    def test_gdb_stops_on_a_myla_line(self):
        session = subprocess.run(
            ["gdb", "-q", "-batch", "-ex", "break prog.my:2", "-ex", "run",
             "-ex", "bt", self.build("-g")],
            capture_output=True, text=True, timeout=60,
        ).stdout
        self.assertIn("let c = a + b", session)          # the source line is shown
        self.assertIn("myla_add () at", session)          # frame in Myla terms
        self.assertIn("prog.my:2", session)
        self.assertIn("myla_main", session)               # the caller in the backtrace


if __name__ == "__main__":
    unittest.main()
