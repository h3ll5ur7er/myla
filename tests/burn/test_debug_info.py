"""Burn tests: `myla build -g` produces DWARF debug information that real tools
read: a line table (MYLA-71), and the variables of every function with their
types (MYLA-66), in both backends. readelf (binutils) is always there when
native builds work; the gdb tests run only where gdb is installed."""
import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest

from myla.cli import main as _cli_main
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON


def myla(argv: list[str]) -> int:
    """The Python CLI in-process, its `wrote <binary>` line kept out of the
    test run's output (MYLA-192)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return _cli_main(argv)

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

    def test_both_backends_embed_the_pretty_printers(self):
        # an inline Python script (kind 4) in .debug_gdb_scripts: src/myla/debug/myla_gdb.py
        from myla.compiler import build
        from myla.loader import link
        from myla.types import check

        def section(binary: str) -> bytes:
            names = subprocess.run(["readelf", "-S", "-W", binary], capture_output=True,
                                   text=True, check=True).stdout
            if ".debug_gdb_scripts" not in names:
                return b""
            raw = os.path.join(self.dir, "scripts.bin")
            subprocess.run(["objcopy", f"--dump-section=.debug_gdb_scripts={raw}", binary,
                            os.path.join(self.dir, "scratch.o")], check=True)
            with open(raw, "rb") as fh:
                return fh.read()

        python = os.path.join(self.dir, "prog_py")
        build(check(link(os.path.join(self.dir, "main.my"), stdlib_root=self.stdlib)), python,
              debug=True)
        with open(GDB_SCRIPT, "rb") as fh:
            expected = b"\x04myla-printers\n" + fh.read() + b"\x00"
        self.assertEqual(section(python), expected)
        self.assertEqual(section(self.build("-g")), expected)
        self.assertEqual(section(self.build()), b"")      # only with -g

    def test_the_compile_unit_names_the_working_directory(self):
        # std.fs.current_dir (MYLA-98), as the Python backend's os.getcwd()
        asm = subprocess.run([self.gen, "main.my", self.stdlib, "-g"], cwd=self.dir,
                             capture_output=True, text=True, check=True).stdout
        binary = os.path.join(self.dir, "prog_cwd")
        with open(binary + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm)
        subprocess.run(["as", "--64", "-o", binary + ".o", binary + ".s"], check=True)
        subprocess.run(["ld", "-o", binary, binary + ".o"], check=True)
        dump = subprocess.run(["readelf", "--debug-dump=info", binary],
                              capture_output=True, text=True, check=True).stdout
        comp_dir = [line for line in dump.splitlines() if "DW_AT_comp_dir" in line]
        self.assertEqual(len(comp_dir), 1, comp_dir)
        self.assertTrue(comp_dir[0].rstrip().endswith(": " + self.dir), comp_dir)

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


def gdb(binary: str, *commands: str, printers: bool = False) -> str:
    """gdb's output for `commands`, run in batch mode on `binary`; with
    `printers`, gdb may auto-load the pretty-printers the binary embeds."""
    args = ["gdb", "-q", "-batch", "-nx"]
    if printers:
        args += ["-iex", f"add-auto-load-safe-path {binary}"]
    for command in commands:
        args += ["-ex", command]
    return subprocess.run(args + [binary], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, timeout=60).stdout


GDB_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir,
                          "src", "myla", "debug", "myla_gdb.py")


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

# Heap values inside aggregates, lists and maps, float32 fields and elements, a
# boxed enum, and functions returning an aggregate, an integer and a string,
# for the pretty-printers and `finish` (MYLA-66).
HEAP = """\
struct Bag {
    items: [int],
    label: str,
    ratio: float,
    tags: [str: int],
}

enum Tree {
    Leaf(int),
    Node(Tree, Tree),
}

fun make_bag(n: int) -> Bag {
    return Bag { items: [n, n + 1], label: "two", ratio: 0.1, tags: ["k": n] }
}

fun total(b: Bag) -> int {
    return b.items[0] + b.items[1]
}

fun greet(name: str) -> str {
    return "hi " + name
}

fun main() {
    let bag = make_bag(4)
    let words = ["a", "b"]
    let m = ["x": 1]
    let names = [1: "one"]
    let pair = (1.5, "p")
    let fs = [0.1, 0.25]
    let tree = Tree.Node(Tree.Leaf(1), Tree.Leaf(2))
    let nested = [[1, 2], [3]]
    print(total(bag))
    print(greet("bo"))
    print(len(words) + len(m) + len(names) + len(pair.1) + len(fs) + len(nested))
    match tree { Node(_, _) => print(1), Leaf(v) => print(v) }
}
"""
HEAP_LOCALS = (
    'bag = Bag {items: [4, 5], label: "two", ratio: 0.100000001, tags: {"k": 4}}',
    'words = ["a", "b"]', 'm = {"x": 1}', 'names = {1: "one"}', 'pair = (1.5, "p")',
    "fs = [0.100000001, 0.25]", "tree = Tree::Node(Tree::Leaf(1), Tree::Leaf(2))",
    "nested = [[1, 2], [3]]",
)


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
        self.assertRegex(session, r"\$4 = \[str: int32\] \{len: 1, cap: \d+, slots: \[")

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

    def test_the_printers_show_heap_values_inside_aggregates(self):
        # the pretty-printers the binary embeds, auto-loaded where allowed
        session = gdb(self.build("heap", HEAP), "break heap.my:34", "run", "info locals",
                      "print *words[1]", "print/r *words[1]", "print bag.tags", printers=True)
        for line in HEAP_LOCALS:
            self.assertIn(line + "\n", session)
        self.assertIn('$1 = "b"\n', session)                        # a cell, dereferenced
        self.assertIn("$2 = str {len: 1, bytes: [98 'b']}\n", session)  # raw: the cell
        self.assertIn('$3 = {"k": 4}\n', session)

    def test_without_the_printers_heap_values_are_pointers(self):
        binary = self.build("heap", HEAP)
        session = gdb(binary, "break heap.my:34", "run", "info locals")
        self.assertIn("auto-loading has been declined", session)    # gdb says why
        self.assertRegex(session, r"bag = Bag \{items: 0x[0-9a-f]+, label: 0x[0-9a-f]+, "
                                  r"ratio: 0.10000000149011612, tags: 0x[0-9a-f]+\}")
        # the same script, loaded by hand
        session = gdb(binary, f"source {GDB_SCRIPT}", "break heap.my:34", "run", "info locals")
        for line in HEAP_LOCALS:
            self.assertIn(line + "\n", session)

    def test_finish_prints_the_value_returned(self):
        session = gdb(self.build("heap", HEAP), "break myla_make_bag", "break myla_total",
                      "break myla_greet", "run", "finish", "continue", "finish", "continue",
                      "finish", printers=True)
        self.assertIn('Value returned is $1 = Bag {items: [4, 5], label: "two", '
                      'ratio: 0.100000001, tags: {"k": 4}}\n', session)
        self.assertIn("Value returned is $2 = 9\n", session)
        self.assertIn('Value returned is $3 = "hi bo"\n', session)

    def test_finish_without_the_printers(self):
        # an aggregate comes back through the hidden pointer %rax returns
        session = gdb(self.build("heap", HEAP), "break myla_make_bag", "break myla_total",
                      "run", "finish", "print *$", "continue", "finish")
        self.assertRegex(session, r"Value returned is \$1 = \(\*mut Bag\) 0x[0-9a-f]+\n")
        self.assertIn("$2 = Bag {items: 0x", session)
        self.assertIn("Value returned is $3 = 9\n", session)


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


# Async functions and an async lambda in a program with tasks: their variables
# live in heap frames (D90, MYLA-141).
TASKS = """\
import std.task as task

async fun greet(name: str, times: int) -> int {
    var count = 0
    let words = ["hi", name]
    for i in 0..times {
        count = count + len(words[1])
    }
    let label = f"{name}!"
    return count + len(label)
}

#main
async fun main() {
    async let a = greet("bo", 3)
    let r = await a
    let base = 40
    var fs: [async () -> int] = []
    push(fs, async () => base + r)
    let rs = await task.all(fs)
    print(r)
    print(rs[0])
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE and shutil.which("gdb"), "needs native builds and gdb")
class TestSelfHostedGdbVariables(GdbVariables, unittest.TestCase):
    """The self-hosted backend (`gen_main … -g`)."""

    @unittest.skipUnless(shutil.which("gdb"), "gdb is not installed")
    def test_async_functions_show_their_variables(self):
        # one worker, so the breakpoints come in a fixed order
        session = gdb(self.build("tasks", TASKS), "set environment MYLA_THREADS 1",
                      "break tasks.my:10", "break tasks.my:18", "rbreak _lam",
                      "run", "info args", "info locals", "continue", "info locals",
                      "print r + 1", "continue", "info locals", printers=True)
        self.assertIn('name = "bo"\ntimes = 3\n', session)
        for line in ("count = 6", 'words = ["hi", "bo"]'):
            self.assertIn(line + "\n", session)
        self.assertIn("r = 9\n", session)       # after the await
        self.assertIn("$1 = 10\n", session)
        self.assertIn("base = 40\n", session)   # the async lambda's capture
        self.assertNotIn("%", session.split("Breakpoint 1,")[-1].split("[Inferior")[0])

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
