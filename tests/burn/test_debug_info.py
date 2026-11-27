"""Burn tests: `myla build -g` produces DWARF debug information that real tools
read: a line table (MYLA-71), and the variables of every function with their
types (MYLA-66), from the self-hosted CLI and compiler. readelf (binutils) is
always there when native builds work; the gdb tests run only where gdb is
installed. (The Python backend's debug information was tested too until it was
retired, MYLA-219; the self-hosted compiler's abbreviation table is still
compared with the one the Python backend wrote, recorded.) On Windows
(MYLA-757) the same DWARF is in the `.exe`'s COFF sections: LLVM's tools,
gdb and lldb read it from the file, gdb under Wine from the running
program; on Windows itself (MYLA-926) the `.exe` runs directly."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tests.burn._golden import golden
from tests.burn._native import (CAN_BUILD_NATIVE, HOST_TARGET, ON_WINDOWS, READS_X86, SKIP_REASON, assemble,
                                linux_only, wine, wine_env)
from tests.burn._tools import STDLIB_ROOT, selfhost_tool


def myla(argv: list[str]) -> int:
    """`myla <argv>` of the natively built CLI (MYLA-235)."""
    return subprocess.run([selfhost_tool("main"), *argv, "--stdlib", STDLIB_ROOT],
                          capture_output=True).returncode


def _abbrev_table(asm: str) -> str:
    """The `.debug_abbrev` section of the assembly `asm`."""
    start = asm.index("\t.section .debug_abbrev")
    return asm[start:asm.index("\t.section .debug_info", start)]


@golden("test_debug_info.python_abbrev_table")
def _python_abbrev_table(entry: str, imported: list[str]) -> str:
    """The abbreviation table the Python backend wrote for the program `entry`
    built with `-g` (`imported`: the files it imports, named so that their
    content is part of the question)."""
    from myla.compiler import compile_to_asm
    from myla.loader import default_stdlib_root, link
    from myla.types import check
    return _abbrev_table(compile_to_asm(check(link(entry, stdlib_root=default_stdlib_root())), debug=True))

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
@unittest.skipUnless(READS_X86, "-g is x86-64 Linux's alone (Language/Targets, MYLA-259)")
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
@unittest.skipUnless(READS_X86, "-g is x86-64 Linux's alone (Language/Targets, MYLA-259)")
class TestSelfHostedLineTables(unittest.TestCase):
    """`gen_main -g` (the self-hosted compiler) emits the same kind of line
    table: one `.file` per module, `.loc` per function, lambda and statement."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.stdlib = STDLIB_ROOT
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
        assemble(binary + ".s", binary)
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
        # selfhost/dwarf.my writes the table src/myla/compiler/dwarf.py wrote
        # (MYLA-66; recorded)
        entry = os.path.join(self.dir, "main.my")
        python = _python_abbrev_table(entry, [os.path.join(self.dir, "lib.my")])
        selfhosted = subprocess.run([self.gen, entry, self.stdlib, "-g"],
                                    capture_output=True, text=True, check=True).stdout
        self.assertEqual(_abbrev_table(selfhosted), python)

    def test_the_pretty_printers_are_embedded(self):
        # an inline Python script (kind 4) in .debug_gdb_scripts: lib/debug/myla_gdb.py
        # (the Python backend embedded it too until it was retired, MYLA-219)
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

        with open(GDB_SCRIPT, "rb") as fh:
            expected = b"\x04myla-printers\n" + fh.read() + b"\x00"
        self.assertEqual(section(self.build("-g")), expected)
        self.assertEqual(section(self.build()), b"")      # only with -g

    def test_the_compile_unit_names_the_working_directory(self):
        # std.fs.current_dir (MYLA-98), as the Python backend's os.getcwd() did
        asm = subprocess.run([self.gen, "main.my", self.stdlib, "-g"], cwd=self.dir,
                             capture_output=True, text=True, check=True).stdout
        binary = os.path.join(self.dir, "prog_cwd")
        with open(binary + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm)
        assemble(binary + ".s", binary)
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


GDB_SCRIPT = os.path.join(STDLIB_ROOT, "debug", "myla_gdb.py")


# Scalars of every kind, a loop variable, shadowing and a match binding.
SCALARS = """\
fun main() {
    let small: int8 = -8
    let wide: uint16 = 65535
    let big: int64 = -1234567890123
    let huge: uint64 = 18446744073709551615
    let f: float32 = 0.1
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
        Dot => label.len()
    }
}

fun main() {
    let name = "hello"
    let xs = [1, -2, 3]; let flags = [true, false, true]
    let cs = ['a', 'b']
    let words = ["ab", "c"]
    let p = Point { x: 3, y: 1.5f64 }
    let t = (7, true)
    let s = Shape.Circle(p, 2)
    let o: Option<int> = Some(4)
    var sb = StringBuilder()
    sb.append("built")
    let k = 10
    let add_k = (n: int) => n + k
    let m = ["a": 1]
    print(area(s, "disk"))
    print(p.moved(4).x)
    print(add_k(1))
    print(m.len() + name.len() + xs.len() + cs.len() + words.len() + t.0 + sb.build().len())
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
    ratio: float32,
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
    let fs: [float32] = [0.1, 0.25]
    let tree = Tree.Node(Tree.Leaf(1), Tree.Leaf(2))
    let nested = [[1, 2], [3]]
    print(total(bag))
    print(greet("bo"))
    print(words.len() + m.len() + names.len() + pair.1.len() + fs.len() + nested.len())
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
        # a [bool]'s elements are one byte each (D120)
        for line in ('name = "hello"', "xs = [1, -2, 3]", "flags = [true, false, true]", "cs = [97 'a', 98 'b']",
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
@unittest.skipUnless(READS_X86, "-g is x86-64 Linux's alone (Language/Targets, MYLA-259)")
class TestGdbVariables(GdbVariables, unittest.TestCase):
    """`myla build -g` of the self-hosted CLI (the Python backend's until
    MYLA-235)."""

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
        count = count + words[1].len()
    }
    let label = f"{name}!"
    return count + label.len()
}

#main
async fun main() {
    async let a = greet("bo", 3)
    let r = await a
    let base = 40
    var fs: [async () -> int] = []
    fs.push(async () => base + r)
    let rs = await task.all(fs)
    print(r)
    print(rs[0])
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE and shutil.which("gdb"), "needs native builds and gdb")
@unittest.skipUnless(READS_X86, "-g is x86-64 Linux's alone (Language/Targets, MYLA-259)")
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
        cls.stdlib = STDLIB_ROOT
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
        assemble(binary + ".s", binary)
        return binary


WINDOWS_TOOLS = ("clang", "llvm-dlltool", "lld-link")
HAVE_WINDOWS_TOOLS = all(shutil.which(t) for t in WINDOWS_TOOLS)
WINDOWS_SKIP = "building for x86_64-windows needs clang, llvm-dlltool and lld-link"

WIN_PROGRAM = (
    "struct Point {\n"                        # line 1
    "    x: int,\n"
    "    y: int,\n"
    "}\n"
    "\n"
    "fun add(a: int, b: int) -> int {\n"      # line 6
    "    let c = a + b\n"                     # line 7
    "    return c\n"                          # line 8
    "}\n"
    "\n"
    "fun main() {\n"                          # line 11
    "    let p = Point { x: 2, y: 3 }\n"      # line 12
    "    let name = \"two\"\n"                # line 13
    "    let xs = [p, Point { x: 4, y: 5 }]\n"
    "    print(add(p.x, p.y))\n"              # line 15
    "    print(name)\n"
    "    print(xs.len())\n"
    "}\n"
)


def _llvm(tool: str, *args: str) -> str:
    return subprocess.run([tool, *args], capture_output=True, text=True, check=True).stdout


def line_rows(exe: str) -> list[tuple[int, str, int]]:
    """The rows of the line table of `exe` as llvm-dwarfdump decodes them:
    (address, file name, line)."""
    files: dict[int, str] = {}
    rows = []
    current = 0
    for line in _llvm("llvm-dwarfdump", "--debug-line", exe).splitlines():
        words = line.split()
        if line.startswith("file_names["):
            current = int(line.split("[")[1].split("]")[0])
        elif words[:1] == ["name:"]:
            files[current] = words[1].strip('"')
        elif len(words) >= 4 and words[0].startswith("0x") and words[1].isdigit():
            rows.append((int(words[0], 16), files.get(int(words[3]), "?"), int(words[1])))
    return rows


def _lldb_cannot_start() -> str | None:
    """Why the lldb on PATH doesn't start (`lldb --version`), or None when it
    does. LLVM's lldb for Windows loads the Python it was built with
    (`python3NN.dll`) as it starts, and where that isn't found ends before
    a word (run 277 on the Windows runner: no output at all, MYLA-926),
    which says nothing of the program it was to read."""
    try:
        p = subprocess.run(["lldb", "--version"], capture_output=True, text=True, timeout=60)
    except OSError as e:
        return f"lldb doesn't start: {e}"
    if p.returncode == 0 and p.stdout.strip():
        return None
    return f"lldb doesn't start: 'lldb --version' ended with {p.returncode & 0xFFFFFFFF:#x}, {p.stderr.strip()!r}"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WINDOWS_TOOLS, WINDOWS_SKIP)
class TestWindowsDebugInfo(unittest.TestCase):
    """`myla build -g --target x86_64-windows` (MYLA-757): the DWARF of Linux's
    `-g` in the COFF sections of the `.exe`, which lld-link keeps
    (`/debug:dwarf`); read by LLVM's tools, gdb and lldb from the file, and by
    gdb from the running program under Wine (winedbg's gdb proxy)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.realpath(tmp.name)
        with open(os.path.join(self.dir, "main.my"), "w", encoding="utf-8") as fh:
            fh.write(WIN_PROGRAM)

    def build(self, *flags: str, out: str = "prog.exe") -> str:
        built = subprocess.run([selfhost_tool("main"), "build", "main.my", "--target", "x86_64-windows", "-o", out,
                                "--stdlib", STDLIB_ROOT, *flags], capture_output=True, text=True, cwd=self.dir,
                               timeout=300)
        self.assertEqual((built.stderr, built.returncode), ("", 0))
        return os.path.join(self.dir, out)

    def subprogram(self, exe: str, name: str) -> str:
        """llvm-dwarfdump's description of the function `name`, its children
        included."""
        return _llvm("llvm-dwarfdump", "--debug-info", f"--name={name}", "--show-children", exe)

    @unittest.skipUnless(shutil.which("llvm-dwarfdump") and shutil.which("llvm-symbolizer"), "needs LLVM's DWARF tools")
    def test_a_functions_address_maps_to_its_line(self):
        exe = self.build("-g")
        low_pc = int(self.subprogram(exe, "myla_add").split("DW_AT_low_pc\t(")[1].split(")")[0], 16)
        rows = line_rows(exe)
        # the line table's row at the function's address is its `fun` line
        self.assertIn((low_pc, "main.my", 6), rows)
        self.assertLessEqual({6, 7, 8, 11, 12, 13, 15, 16, 17}, {line for _, f, line in rows if f == "main.my"})
        # LLVM's symbolizer says so too, with the function's name
        said = _llvm("llvm-symbolizer", f"--obj={exe}", hex(low_pc)).split()
        self.assertEqual((said[0], said[1].replace("\\", "/")), ("myla_add", self.dir.replace("\\", "/") + "/main.my:6:1"))

    @unittest.skipUnless(shutil.which("llvm-dwarfdump"), "needs llvm-dwarfdump")
    def test_functions_variables_and_their_types(self):
        exe = self.build("-g")
        add = " ".join(self.subprogram(exe, "myla_add").split())
        for name in ("a", "b"):
            self.assertIn(f'DW_TAG_formal_parameter DW_AT_name ("{name}") DW_AT_type (0x', add)
        self.assertIn('DW_TAG_variable DW_AT_name ("c") DW_AT_type (0x', add)
        self.assertIn('"int32"', add)
        main = " ".join(self.subprogram(exe, "myla_main").split())
        for name, ty in (("p", "Point"), ("name", "&str"), ("xs", "Point[]")):
            self.assertRegex(main, re.escape(f'DW_TAG_variable DW_AT_name ("{name}") DW_AT_type (0x') + "[0-9a-f]+ "
                             + re.escape(f'"{ty}")'))
        # the offsets into other sections are their own (`.secrel32`): the
        # whole unit reads back without an error
        verified = subprocess.run(["llvm-dwarfdump", "--verify", exe], capture_output=True, text=True)
        self.assertEqual((verified.returncode, "No errors." in verified.stdout), (0, True), verified.stdout[-2000:])

    @unittest.skipUnless(shutil.which("llvm-objdump"), "needs llvm-objdump")
    def test_the_sections_only_with_g(self):
        def sections(exe: str) -> list[str]:
            return [words[1] for words in (line.split() for line in _llvm("llvm-objdump", "-h", exe).splitlines())
                    if len(words) > 2 and words[0].isdigit()]
        debug = sections(self.build("-g"))
        for name in (".debug_abbrev", ".debug_info", ".debug_line", ".debug_gdb_scripts"):
            self.assertIn(name, debug)
        plain = sections(self.build(out="plain.exe"))
        self.assertEqual([s for s in plain if s.startswith(".debug")], [])
        # the code's sections are the same ones: what the program doesn't
        # call is left out under -g too (`/opt:ref`)
        self.assertEqual([s for s in debug if not s.startswith(".debug")], plain)
        # DWARF in the image, no PDB: nothing beside the programs (MYLA-35)
        self.assertEqual(sorted(os.listdir(self.dir)), ["main.my", "plain.exe", "prog.exe"])

    @unittest.skipUnless(shutil.which("llvm-objcopy"), "needs llvm-objcopy")
    def test_the_pretty_printers_are_embedded(self):
        raw = os.path.join(self.dir, "scripts.bin")
        subprocess.run(["llvm-objcopy", f"--dump-section=.debug_gdb_scripts={raw}", self.build("-g"),
                        os.path.join(self.dir, "scratch.exe")], check=True)
        with open(raw, "rb") as fh:
            got = fh.read()
        with open(GDB_SCRIPT, "rb") as fh:
            want = b"\x04myla-printers\n" + fh.read() + b"\x00"
        # (a PE section's bytes are padded to the file's alignment)
        self.assertEqual(got[:len(want)], want)
        self.assertEqual(got[len(want):].strip(b"\0"), b"")

    @unittest.skipUnless(shutil.which("gdb"), "gdb is not installed")
    @unittest.skipUnless(HOST_TARGET == "x86_64-linux", "the machine's gdb reads x86-64 executables (an x86-64 host)")
    def test_gdb_reads_the_exe(self):
        session = gdb(self.build("-g"), "info line myla_add", "break main.my:7", "info scope myla_add",
                      "info auto-load python-scripts", printers=True)
        self.assertRegex(session, r'Line 6 of "main.my" starts at address 0x[0-9a-f]+ <myla_add>')
        self.assertRegex(session, r"Breakpoint 1 at 0x[0-9a-f]+: file main.my, line 7\.")
        self.assertIn("Symbol a is a variable at frame base reg $rbp offset 0+-", session)
        # gdb finds the printers in the PE file's section as in an ELF file's
        self.assertRegex(session, r"Yes\s+myla-printers")

    @unittest.skipUnless(shutil.which("lldb"), "lldb is not installed")
    def test_lldb_reads_the_exe(self):
        cannot = _lldb_cannot_start()
        if cannot:
            self.skipTest(cannot)
        session = subprocess.run(["lldb", "-b", "-o", "image lookup -n myla_add -v", "-o", "breakpoint set -f main.my -l 7",
                                  self.build("-g")], capture_output=True, text=True, timeout=120).stdout
        self.assertIn("`myla_add at main.my:6:1", session)
        self.assertIn('name = "a", type = "int32"', session)
        self.assertRegex(session, r"Breakpoint 1: where = prog\.exe`myla_add \+ \d+ at main\.my:7:5")

    @unittest.skipUnless(ON_WINDOWS or wine(), "Wine is not installed")
    def test_it_runs_as_without_g(self):
        # under Wine here, on Windows itself there (MYLA-926)
        runner = [] if ON_WINDOWS else wine()
        if not ON_WINDOWS:
            wine_env()
        for exe in (self.build(out="plain.exe"), self.build("-g")):
            ran = subprocess.run([*runner, exe], capture_output=True, cwd=self.dir, timeout=120)
            self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"5\ntwo\n2\n", b"", 0))

    @linux_only("Wine's winedbg and a #!/bin/sh gdb")
    @unittest.skipUnless(wine() and shutil.which("gdb"), "needs Wine and gdb")
    def test_gdb_on_the_running_program_under_wine(self):
        # winedbg --gdb starts the program under its gdb proxy, then `gdb`
        # from PATH with a file of commands that attaches to it: here a gdb
        # that runs those, then this test's, in batch mode
        wine_env()
        exe = self.build("-g")
        bindir = os.path.join(self.dir, "bin")
        os.makedirs(bindir)
        commands = ["break main.my:7", "continue", "info args", "bt", "up", "info locals", "down", "finish", "kill"]
        with open(os.path.join(bindir, "gdb"), "w", encoding="utf-8") as fh:
            fh.write(f"#!/bin/sh\nexec {shutil.which('gdb')} -q -batch -nx -iex 'add-auto-load-safe-path {exe}' \"$@\" "
                     + " ".join(f"-ex '{c}'" for c in commands) + "\n")
        os.chmod(os.path.join(bindir, "gdb"), 0o755)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""))
        session = subprocess.run([*wine(), "winedbg", "--gdb", "Z:" + exe.replace("/", "\\")], env=env, cwd=self.dir,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, timeout=180).stdout
        self.assertIn("Breakpoint 1, myla_add (a=2, b=3) at main.my:7\n7\t    let c = a + b\n", session)
        self.assertIn("a = 2\nb = 3\n", session)
        self.assertRegex(session, r"#1  0x[0-9a-f]+ in myla_main \(\) at main\.my:15")
        # the printers the .exe carries show the heap values
        self.assertIn('xs = [Point {x: 2, y: 3}, Point {x: 4, y: 5}]\nname = "two"\np = Point {x: 2, y: 3}\n', session)
        self.assertIn("Value returned is $1 = 5\n", session)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestWithoutG(unittest.TestCase):
    """Without `-g` no target's assembly has debug information: the build
    without it stays as it was (MYLA-757 made `-g` work on Windows)."""

    def test_no_target_has_debug_directives_without_g(self):
        with tempfile.TemporaryDirectory() as d:
            source = os.path.join(d, "main.my")
            with open(source, "w", encoding="utf-8") as fh:
                fh.write(WIN_PROGRAM)
            for target in ("x86_64-linux", "aarch64-linux", "wasm32-wasi", "x86_64-windows"):
                asm = subprocess.run([selfhost_tool("gen_main"), source, STDLIB_ROOT, "--target", target],
                                     capture_output=True, text=True, check=True).stdout
                for word in ("\t.loc ", "\t.file ", ".debug_", ".secrel32", ".Ltext0"):
                    self.assertNotIn(word, asm, f"{target}: {word.strip()}")


if __name__ == "__main__":
    unittest.main()
