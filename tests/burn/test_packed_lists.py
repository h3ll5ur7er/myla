"""Burn test: list elements at their natural size (D120, MYLA-247).

A `[bool]` keeps one byte per element: read and written by index (nested
too), pushed across every growth, popped, iterated, matched, built from a
literal, copied on write, passed and returned, held in a struct, made by a
map's `keys()` and handed to a task. Lists of 8-, 16-, 32- and 64-bit
integers (signed values sign-extended, wrapping at their width), `char`
(from `chars()` too), `float32`, a map's integer keys and a process's
output bytes likewise. Natively they print what the interpreter prints
(checked against Python's computation), with loads and stores of the
element's width."""
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

_WIDTHS = """from std.process import run

fun sum8(xs: [int8]) -> int64 {
    var t: int64 = 0
    for x in xs {
        t = t * 7 + (x as int64)
    }
    return t
}

fun sum16(xs: [uint16]) -> int64 {
    var t: int64 = 0
    for x in xs {
        t = t * 7 + (x as int64)
    }
    return t
}

fun sum32(xs: [int]) -> int64 {
    var t: int64 = 0
    for x in xs {
        t = (t * 31 + (x as int64)) % 1000000007
    }
    return t
}

fun main() {
    // int8: sign extension, wrapping at the width
    var a: [int8] = [-128, -1, 0, 1, 127]
    a[1] = a[1] - 1
    a[4] = a[4] + 1
    a.push(-5)
    print(sum8(a))
    print(a[4])
    print(a.pop())
    // uint8 and uint16: zero extension
    var b: [uint8] = [255, 0, 128]
    b[0] = b[0] + 1
    b[2] += 1
    print(b[0])
    print(b[2])
    var c: [uint16] = [65535, 1, 2]
    c[1] += 65535
    print(sum16(c))
    // int (int32), with compound assignment and growth
    var d: [int] = []
    for i in 0..1000 {
        d.push(i * 1000003 - 500000000)
    }
    d[3] += 7
    d[999] = -2147483648
    print(sum32(d))
    print(d[999])
    var e = d
    e[0] = 42
    print(d[0])
    print(e[0])
    // int64 and uint32
    var g: [int64] = [9000000000i64, -9000000000i64]
    print(g[0] + g[1])
    var h: [uint32] = [4294967295u32, 7u32]
    print(h[0])
    print(h[1] + 1u32)
    // char: a literal, chars(), indexing
    let cs = "aé€😀".chars()
    print(cs.len())
    for ch in cs {
        print(ch as uint32)
    }
    var lit = ['x', 'y']
    lit[1] = 'z'
    print(lit[1])
    // float32 and float64
    var f: [float32] = [1.5f32, -2.25f32, 0.1f32]
    f[2] = f[2] + 1.0f32
    f.push(3.0f32)
    print(f[2])
    print(f[0] + f[1] + f[3])
    var q: [float64] = [0.1, 0.2]
    print(q[0] + q[1])
    // maps' keys
    var m: [int: str] = [:]
    m[-3] = "a"
    m[70000] = "b"
    let ks = m.keys()
    print(ks[0])
    print(ks[1])
    var m8: [uint8: int] = [:]
    m8[200u8] = 1
    m8[3u8] = 2
    let k8 = m8.keys()
    print(k8[0])
    print(k8[1])
    // a process's output, a byte an element
    match run("/bin/echo", ["hi", "there"]) {
        Ok(out) => {
            print(out.stdout.len())
            var sb = StringBuilder()
            for byte in out.stdout {
                sb.append_byte(byte)
            }
            print(sb.build())
        },
        Err(e) => { print("no echo") },
    }
}
"""

WIDTHS_EXPECTED = """-2156950
-128
-5
0
129
3211217
-904830087
-2147483648
-500000000
42
0
4294967295
8
4
97
233
8364
128512
z
1.10000002
2.25
0.30000000000000004
-3
70000
200
3
9
hi there

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

    def test_lists_of_every_width_print_the_same(self):
        path = self.same("widths", _WIDTHS, WIDTHS_EXPECTED)
        asm = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT], capture_output=True, text=True,
                             check=True).stdout
        self.assertRegex(_function(asm, "sum8"), r"movsbq 16\(%rax,%rcx,1\)")
        self.assertRegex(_function(asm, "sum16"), r"movzwl 16\(%rax,%rcx,2\)")
        self.assertRegex(_function(asm, "sum32"), r"movslq 16\(%rax,%rcx,4\)")

    def test_bool_lists_in_tasks_print_the_same(self):
        self.same("tasks", _TASKS, "25\n24\n")


if __name__ == "__main__":
    unittest.main()
