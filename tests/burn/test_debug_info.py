"""Burn tests: `myla build -g` produces DWARF debug information that real tools
read: a line table (MYLA-71), and the variables of every function with their
types (MYLA-66), in both backends. readelf (binutils) is always there when
native builds work; the gdb tests run only where gdb is installed."""
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
        session = gdb(self.build("-g"), "break prog.my:2", "run", "bt")
        self.assertIn("let c = a + b", session)          # the source line is shown
        self.assertIn("myla_add (a=2, b=3) at", session)  # frame in Myla terms, with arguments
        self.assertIn("prog.my:2", session)
        self.assertIn("myla_main", session)               # the caller in the backtrace

    @unittest.skipUnless(shutil.which("gdb"), "gdb is not installed")
    def test_gdb_shows_arguments_and_locals(self):
        session = gdb(self.build("-g"), "break prog.my:3", "run", "info args", "info locals")
        self.assertIn("a = 2\nb = 3\nc = 5\n", session)


# The same program with `add` in an imported module and a lambda, for the
# self-hosted compiler's line tables (MYLA-71).
MODULE_MAIN = (
    "from .lib import add\n"                  # line 1
    "fun main() {\n"                           # line 2
    "    let twice = (x: int) => x * 2\n"     # line 3
    "    print(twice(add(2, 3)))\n"           # line 4
    "}\n"
)
MODULE_LIB = (
    "pub fun add(a: int, b: int) -> int {\n"  # line 1
    "    let c = a + b\n"                      # line 2
    "    return c\n"                           # line 3
    "}\n"
)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestSelfHostedLineTables(unittest.TestCase):
    """`gen_main -g` (the self-hosted compiler) emits the same kind of line
    table: one `.file` per module, `.loc` per function, lambda and statement."""

    @classmethod
    def setUpClass(cls):
        from myla.loader import default_stdlib_root

        from ._tools import selfhost_tool

        cls.tmp = tempfile.TemporaryDirectory()
        cls.stdlib = default_stdlib_root()
        cls.gen = selfhost_tool("gen_main")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.realpath(tmp.name)
        for name, text in (("main.my", MODULE_MAIN), ("lib.my", MODULE_LIB)):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8") as fh:
                fh.write(text)

    def build(self, *flags: str) -> str:
        asm = subprocess.run([self.gen, os.path.join(self.dir, "main.my"), self.stdlib, *flags],
                             capture_output=True, text=True, check=True).stdout
        binary = os.path.join(self.dir, "prog" + "".join(flags).replace("-", "_"))
        with open(binary + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm)
        subprocess.run(["as", "--64", "-o", binary + ".o", binary + ".s"], check=True)
        subprocess.run(["ld", "-o", binary, binary + ".o"], check=True)
        return binary

    def test_readelf_sees_the_lines_of_every_module(self):
        dump = subprocess.run(
            ["readelf", "--debug-dump=decodedline", self.build("-g")],
            capture_output=True, text=True, check=True,
        ).stdout
        rows = {tuple(line.split()[:2]) for line in dump.splitlines()
                if line.startswith(("main.my", "lib.my"))}
        for row in (("main.my", "2"), ("main.my", "3"), ("main.my", "4"),
                    ("lib.my", "1"), ("lib.my", "2"), ("lib.my", "3")):
            self.assertIn(row, rows)

    def test_line_tables_do_not_change_behaviour(self):
        plain = subprocess.run([self.build()], capture_output=True, text=True)
        debug = subprocess.run([self.build("-g")], capture_output=True, text=True)
        self.assertEqual((plain.stdout, plain.returncode), ("10\n", 0))
        self.assertEqual((debug.stdout, debug.returncode), (plain.stdout, plain.returncode))

    def test_the_abbreviation_tables_agree(self):
        # selfhost/dwarf.my writes the table src/myla/compiler/dwarf.py writes (MYLA-66)
        from myla.compiler import compile_to_asm
        from myla.loader import link
        from myla.types import check

        def table(asm: str) -> str:
            start = asm.index("\t.section .debug_abbrev")
            return asm[start:asm.index("\t.section .debug_info", start)]

        entry = os.path.join(self.dir, "main.my")
        python = compile_to_asm(check(link(entry, stdlib_root=self.stdlib)), debug=True)
        selfhosted = subprocess.run([self.gen, entry, self.stdlib, "-g"],
                                    capture_output=True, text=True, check=True).stdout
        self.assertEqual(table(selfhosted), table(python))

    def test_without_g_there_are_no_line_directives(self):
        asm = subprocess.run([self.gen, os.path.join(self.dir, "main.my"), self.stdlib],
                             capture_output=True, text=True, check=True).stdout
        self.assertNotIn(".loc", asm)
        self.assertNotIn(".file", asm)

    @unittest.skipUnless(shutil.which("gdb"), "gdb is not installed")
    def test_gdb_stops_on_a_line_of_an_imported_module(self):
        session = subprocess.run(
            ["gdb", "-q", "-batch", "-ex", "break lib.my:2", "-ex", "run",
             "-ex", "bt", self.build("-g")],
            capture_output=True, text=True, timeout=60,
        ).stdout
        self.assertIn("let c = a + b", session)
        self.assertIn("lib.my:2", session)
        self.assertIn("main.my:4", session)                # the caller's line


def gdb(binary: str, *commands: str) -> str:
    """gdb's output for `commands`, run in batch mode on `binary`."""
    args = ["gdb", "-q", "-batch", "-nx"]
    for command in commands:
        args += ["-ex", command]
    return subprocess.run(args + [binary], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, timeout=60).stdout


# Scalars of every kind, a loop variable, shadowing and a match binding.
SCALARS = """\
fun main() {
    let small: int8 = -8
    let wide: uint16 = 65535
    let big: int64 = -1234567890123
    let huge: uint64 = 18446744073709551615
    let f: float = 0.1
    let d: float64 = 2.5f64
    let yes = true
    let ch = '\\u{e9}'
    var total = 0
    for k in 0..3 {
        total = total + k
    }
    let x = 1
    if yes {
        let x = 2
        print(x)
    }
    match Some(7) {
        Some(v) => print(v + x)
        None => print(0)
    }
}
"""

# Strings, lists, structs, tuples, enums, a builder, a map, parameters passed by
# address, `self`, and a lambda's parameter and capture.
VALUES = """\
struct Point {
    x: int,
    y: float64,
}

enum Shape {
    Circle(Point, int),
    Dot,
}

impl Point {
    fun moved(self, dx: int) -> Point {
        return Point { x: self.x + dx, y: self.y }
    }
}

fun area(s: Shape, label: str) -> int {
    return match s {
        Circle(c, r) => r * r + c.x
        Dot => len(label)
    }
}

fun main() {
    let name = "hello"
    let xs = [1, -2, 3]
    let cs = ['a', 'b']
    let words = ["ab", "c"]
    let p = Point { x: 3, y: 1.5f64 }
    let t = (7, true)
    let s = Shape.Circle(p, 2)
    let o: Option<int> = Some(4)
    var sb = StringBuilder()
    append(sb, "built")
    let k = 10
    let add_k = (n: int) => n + k
    let m = ["a": 1]
    print(area(s, "disk"))
    print(p.moved(4).x)
    print(add_k(1))
    print(len(m) + len(name) + len(xs) + len(cs) + len(words) + t.0 + len(build(sb)))
    match o { Some(v) => print(v), None => print(0) }
}
"""


class GdbVariables:
    """What gdb shows of the variables in a `-g` build (MYLA-66): `build(name,
    source)` returns the binary of `source` written as `<name>.my`."""

    def build(self, name: str, source: str) -> str:
        raise NotImplementedError

    def test_scalars_of_every_kind(self):
        session = gdb(self.build("scalars", SCALARS), "break scalars.my:14", "run", "info locals",
                      "print x")
        for line in ("small = -8", "wide = 65535", "big = -1234567890123",
                     "huge = 18446744073709551615", "f = 0.100000001", "d = 2.5", "yes = true",
                     "total = 3"):
            self.assertIn(line + "\n", session)
        self.assertRegex(session, r"ch = 233 '(\u00e9|\\xe9)'\n")  # as the locale allows
        self.assertNotIn("\nk = ", session)       # the loop variable's scope has ended
        self.assertNotIn("\nx = ", session)       # not declared yet
        self.assertRegex(session, r"No symbol .x. in current context")

    def test_values_change_while_stepping(self):
        session = gdb(self.build("scalars", SCALARS), "break scalars.my:12", "run",
                      "print k", "print total", "continue", "print k", "print total",
                      "next", "print total")
        self.assertIn("$1 = 0\n$2 = 0\n", session)
        self.assertIn("$3 = 1\n$4 = 0\n", session)
        self.assertIn("$5 = 1\n", session)

    def test_shadowing_and_scopes(self):
        session = gdb(self.build("scalars", SCALARS), "break scalars.my:17", "break scalars.my:20",
                      "run", "print x", "info locals", "continue", "print x", "print v")
        self.assertIn("$1 = 2\n", session)        # the inner `x`
        self.assertIn("x = 2\nx = 1\n", session)  # innermost first, the shadowed one after
        self.assertIn("$2 = 1\n$3 = 7\n", session)  # back to the outer `x`; the match binding

    def test_strings_lists_and_aggregates(self):
        session = gdb(self.build("values", VALUES), "break values.my:38", "run", "info locals",
                      "print xs[1]", "print p.x + 1", "print *words[1]", "print *m")
        for line in ('name = "hello"', "xs = [1, -2, 3]", "cs = [97 'a', 98 'b']",
                     "p = Point {x: 3, y: 1.5}", "t = (7, true)",
                     "s = Shape::Circle(Point {x: 3, y: 1.5}, 2)", "o = Option<int32>::Some(4)",
                     'sb = "built"', "k = 10"):
            self.assertIn(line + "\n", session)
        self.assertIn("$1 = -2\n$2 = 4\n", session)
        self.assertRegex(session, r"\$3 = str \{len: 1, bytes: \[99 'c'\]\}")
        self.assertRegex(session, r"\$4 = \[str: int32\] \{len: 1, cap: \d+\}")

    def test_set_var_writes_a_value_the_program_reads(self):
        # a signed slot is described whole, so a negative value is written
        # sign-extended and the program's 64-bit comparison sees it
        source = "fun main() {\n    var c = 5\n    print(c)\n    if c < 0 { print(-1) } else { print(1) }\n}\n"
        session = gdb(self.build("setvar", source), "break setvar.my:3", "run",
                      "set var c = -3", "continue")
        self.assertIn("-3\n-1\n", session)

    def test_parameters_by_address_and_lambdas(self):
        session = gdb(self.build("values", VALUES), "break values.my:19", "break values.my:13",
                      "rbreak _lam", "run", "info args", "continue", "info args",
                      "continue", "info args", "info locals")
        self.assertIn('s = Shape::Circle(Point {x: 3, y: 1.5}, 2)\nlabel = "disk"\n', session)
        self.assertIn("self = Point {x: 3, y: 1.5}\ndx = 4\n", session)
        self.assertIn("n = 1\n", session)        # the lambda's parameter
        self.assertIn("k = 10\n", session)       # its capture


@unittest.skipUnless(CAN_BUILD_NATIVE and shutil.which("gdb"), "needs native builds and gdb")
class TestGdbVariables(GdbVariables, unittest.TestCase):
    """The Python backend."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.realpath(tmp.name)

    def build(self, name: str, source: str) -> str:
        path = os.path.join(self.dir, name + ".my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)
        binary = os.path.join(self.dir, name)
        self.assertEqual(myla(["build", path, "-o", binary, "-g"]), 0)
        return binary


@unittest.skipUnless(CAN_BUILD_NATIVE and shutil.which("gdb"), "needs native builds and gdb")
class TestSelfHostedGdbVariables(GdbVariables, unittest.TestCase):
    """The self-hosted backend (`gen_main … -g`)."""

    @classmethod
    def setUpClass(cls):
        from myla.loader import default_stdlib_root

        from ._tools import selfhost_tool

        cls.stdlib = default_stdlib_root()
        cls.gen = selfhost_tool("gen_main")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.realpath(tmp.name)

    def build(self, name: str, source: str) -> str:
        path = os.path.join(self.dir, name + ".my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)
        asm = subprocess.run([self.gen, path, self.stdlib, "-g"],
                             capture_output=True, text=True, check=True).stdout
        binary = os.path.join(self.dir, name)
        with open(binary + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm)
        subprocess.run(["as", "--64", "-o", binary + ".o", binary + ".s"], check=True)
        subprocess.run(["ld", "-o", binary, binary + ".o"], check=True)
        return binary


if __name__ == "__main__":
    unittest.main()
