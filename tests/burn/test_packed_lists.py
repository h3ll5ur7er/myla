"""Burn test: list elements at their natural size (D120, MYLA-247).

A `[bool]` keeps one byte per element: read and written by index (nested
too), pushed across every growth, popped, iterated, matched, built from a
literal, copied on write, passed and returned, held in a struct, made by a
map's `keys()` and handed to a task. Natively it prints what the
interpreter prints, and its loads and stores are one byte wide."""
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """struct Board {
    cells: [bool],
    name: str,
}

fun flip_all(xs: [bool]) -> [bool] {
    var out = xs
    for i in 0..out.len() {
        out[i] = !out[i]
    }
    return out
}

fun count(xs: [bool]) -> int {
    var n = 0
    for x in xs {
        if x {
            n += 1
        }
    }
    return n
}

fun code(xs: [bool]) -> int64 {
    var h: int64 = 7
    var i = 0
    while i < xs.len() {
        h = (h * 3 + (match xs[i] { true => 1i64, false => 2i64 })) % 1000000007
        i += 1
    }
    return h
}

fun main() {
    let lit = [true, false, true, true, false]
    print(count(lit))
    print(code(lit))
    // pushed across every growth, then popped back
    var xs: [bool] = []
    for i in 0..1000 {
        xs.push(i % 3 == 0 || i % 7 == 0)
    }
    print(xs.len())
    print(count(xs))
    print(code(xs))
    var popped = 0
    for i in 0..10 {
        if xs.pop() {
            popped += 1
        }
    }
    print(popped)
    print(xs.len())
    // copied on write: the original keeps its elements
    let before = xs
    xs[0] = false
    xs[1] = true
    print(before[0])
    print(before[1])
    print(xs[0])
    print(xs[1])
    let flipped = flip_all(xs)
    print(count(flipped) + count(xs))
    // neighbours untouched by a write
    var row = [false, false, false, false, false, false, false, false, false]
    row[4] = true
    print(code(row))
    row[4] = false
    row[8] = true
    print(code(row))
    // nested
    var grid: [[bool]] = []
    for r in 0..20 {
        var line: [bool] = []
        for c in 0..20 {
            line.push((r * c) % 5 == 1)
        }
        grid.push(line)
    }
    grid[3][4] = !grid[3][4]
    grid[19][19] = true
    var on = 0
    for line in grid {
        on += count(line)
    }
    print(on)
    print(grid[3][4])
    // in a struct
    var b = Board { cells: [false, true], name: "b" }
    b.cells.push(true)
    b.cells[0] = true
    print(count(b.cells))
    print(b.name)
    // a map's keys
    var m: [bool: int] = [:]
    m[true] = 1
    m[false] = 2
    let ks = m.keys()
    print(ks.len())
    print(code(ks))
    var total = 0
    for k in m {
        if k {
            total += 10
        } else {
            total += 1
        }
    }
    print(total)
    // an empty one
    var none: [bool] = []
    print(count(none))
    none.push(true)
    print(none[0])
}
"""

EXPECTED = """3
1850
1000
429
746778728
5
990
true
false
false
true
990
157382
157462
65
true
3
b
2
68
11
0
true
"""

_TASKS = """import std.task as task

async fun tally(xs: [bool]) -> int {
    var n = 0
    for x in xs {
        if x {
            n += 1
        }
    }
    return n
}

#main
async fun main() {
    var xs: [bool] = []
    for i in 0..100 {
        xs.push(i % 4 == 1)
    }
    async let a = tally(xs)
    xs[1] = false
    let b = await tally(xs)
    print(await a)
    print(b)
}
"""


def _function(asm: str, name: str) -> str:
    m = re.search(rf"^myla_{name}:\n(.*?)(?=^myla_[\w.]+:|\Z)", asm, re.S | re.M)
    if not m:
        raise AssertionError(f"no function {name}")
    return m.group(1)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class PackedLists(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def same(self, name: str, text: str, expected: str) -> str:
        path = os.path.join(self.tmp.name, name + ".my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        myla = selfhost_tool("main")
        ran = subprocess.run([myla, "run", path], capture_output=True, text=True)
        self.assertEqual((ran.stdout, ran.returncode), (expected, 0), ran.stderr)
        exe = os.path.join(self.tmp.name, name)
        built = subprocess.run([myla, "build", path, "-o", exe], capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        native = subprocess.run([exe], capture_output=True, text=True)
        self.assertEqual((native.stdout, native.returncode), (expected, 0), native.stderr)
        return path

    def test_bool_lists_print_the_same(self):
        path = self.same("bools", _PROGRAM, EXPECTED)
        asm = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT], capture_output=True, text=True,
                             check=True).stdout
        # one byte per element: read zero-extended, written as a byte
        self.assertIn("movzbl 16(%rax,%rcx,1)", _function(asm, "code"))
        self.assertRegex(_function(asm, "flip_all"), r"movb %\w+, ")
        self.assertNotIn("16(%rax,%rcx,8)", _function(asm, "count"))

    def test_bool_lists_in_tasks_print_the_same(self):
        self.same("tasks", _TASKS, "25\n24\n")


if __name__ == "__main__":
    unittest.main()
