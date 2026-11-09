"""Burn test: slices and `^` from the end (D142, D143, MYLA-280).

`xs[^n]` is the n-th element from the end; `xs[a:b]`, `xs[a:]`, `xs[:b]` and
`xs[a:b:step]` are new lists (or strings) of the elements a slice takes, the
bounds possibly `^n` too, clamped to the list, the step a signed integer
(negative goes backwards). A `str` is sliced by bytes: a bound strictly
inside a well-formed character is a runtime error (D174), one beside bytes
that are no character isn't. The index arithmetic is Myla (`std.slice`), so
the interpreter and every backend take the same elements."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_argv, run_source_both_now, target_flags
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

PROGRAM = """fun shown(xs: [int]) -> str {
    var sb = StringBuilder()
    sb.append("[")
    var first = true
    for x in xs {
        if !first {
            sb.append(", ")
        }
        sb.append(f"{x}")
        first = false
    }
    sb.append("]")
    return sb.build()
}

fun main() {
    let xs = [10, 20, 30, 40, 50]
    print(xs[^1])
    print(xs[^5])
    print(shown(xs[1:3]))
    print(shown(xs[:2]))
    print(shown(xs[3:]))
    print(shown(xs[1:^1]))
    print(shown(xs[^2:]))
    print(shown(xs[::2]))
    print(shown(xs[::-1]))
    print(shown(xs[^1:0:-2]))
    print(shown(xs[2:99]))
    print(shown(xs[5:2]))
    print(shown(xs[^9:2]))
    print(shown(xs[:]))
    let k = 2
    print(shown(xs[k:k + 2]))
    print(shown(xs[^k:]))
    var ys = [1, 2, 3]
    ys[^1] = 9
    print(shown(ys))
    let names = ["ann", "bob", "cy"]
    print(names[1:][0])
    let grid = [[1, 2, 3], [4, 5, 6]]
    print(shown(grid[^1][1:]))
    let s = "hello, world"
    print(s[^1])
    print(s[0:5])
    print(s[7:])
    print(s[::-1])
    print(s[::3])
    let t = "größe"
    print(t[0:2])
    print(t[2:4])
    print(t[^3:])
}
"""

WANT = """50
10
[20, 30]
[10, 20]
[40, 50]
[20, 30, 40]
[40, 50]
[10, 30, 50]
[50, 40, 30, 20, 10]
[50, 30]
[30, 40, 50]
[]
[10, 20]
[10, 20, 30, 40, 50]
[30, 40]
[40, 50]
[1, 2, 9]
bob
[5, 6]
100
hello
world
dlrow ,olleh
hl r
gr
ö
ße
"""


# D174 (MYLA-390): a str holding bytes that are no character, sliced beside
# them; refused only strictly inside a well-formed character
BYTES = """// D174 (MYLA-390): a bound is refused only strictly inside a well-formed
// character; beside bytes that belong to none, a slice takes them
fun bytes(bs: [int]) -> str {
    var sb = StringBuilder()
    for b in bs { sb.append_byte(b as uint8) }
    return sb.build()
}

fun shown(s: str) -> str {
    var sb = StringBuilder()
    for i in 0..s.len() {
        if i > 0 { sb.append(" ") }
        sb.append(f"{s[i]:02x}")
    }
    return sb.build()
}

fun main() {
    // A, two stray continuation bytes, B, é, C, a cut-short €, an overlong
    // form of '/', a surrogate's encoding, F4 90 (past U+10FFFF), D
    let s = bytes([0x41, 0x80, 0x81, 0x42, 0xC3, 0xA9, 0x43, 0xE2, 0x82, 0xC0, 0xAF, 0xED, 0xA0, 0x80, 0xF4, 0x90, 0x80, 0x80, 0x44])
    print(s.len())
    print(shown(s[1:3]))
    print(shown(s[0:2]))
    print(shown(s[2:4]))
    print(s[4:6])
    print(shown(s[7:9]))
    print(shown(s[8:]))
    print(shown(s[10:11]))
    print(shown(s[12:13]))
    print(shown(s[15:17]))
    print(shown(s[^2:]))
    // a DNS name's labels: a length byte, then that many bytes
    let wire = bytes([3, 0x77, 0x77, 0x77, 0x85, 0x61, 0xC3, 0xA9, 0x80, 0x62, 0])
    print(shown(wire[1:4]))
    print(shown(wire[5:10]))
    print(shown(wire[8:9]))
    let t = "größe"
    print(t[0:2])
    print(t[^3:])
}
"""

BYTES_WANT = """19
80 81
41 80
81 42
é
e2 82
82 c0 af ed a0 80 f4 90 80 80 44
af
a0
90 80
80 44
77 77 77
61 c3 a9 80 62
80
gr
ße
"""

@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Slices(unittest.TestCase):
    def test_in_the_interpreter_and_natively(self):
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_bytes_that_are_no_character(self):
        self.assertEqual(run_source_both_now(BYTES), (BYTES_WANT, "", 0))

    def test_runtime_errors(self):
        cases = {
            "zero_step": ("fun main() {\n    let xs = [1, 2]\n    let s = 0\n    print(xs[::s].len())\n}\n", "slice step is zero"),
            "inside_a_character": ("fun main() {\n    let t = \"größe\"\n    print(t[0:3])\n}\n", "a slice bound inside a character"),
            # D174: a well-formed character among bytes that are none
            "inside_a_character_among_bytes": ("fun main() {\n    var sb = StringBuilder()\n    for b in [0x80, 0xC3, 0xA9, 0xFF] { sb.append_byte(b as uint8) }\n    let s = sb.build()\n    print(s[2:].len())\n}\n", "a slice bound inside a character"),
            "a_step_over_a_character": ("fun main() {\n    let t = \"aö\"\n    print(t[::-1])\n}\n", "a slice bound inside a character"),
            "past_the_start": ("fun main() {\n    let xs = [1, 2]\n    print(xs[^3])\n}\n", "out of bounds"),
            "zero_from_the_end": ("fun main() {\n    let xs = [1, 2]\n    print(xs[^0])\n}\n", "out of bounds"),
            # a plain negative bound, as a negative index (D154: it meant
            # "before the start" and hid the slip `^` catches)
            "a_negative_stop": ("fun main() {\n    let xs = [1, 2, 3]\n    print(xs[1:-1].len())\n}\n", "index out of bounds"),
            "a_negative_start": ("fun main() {\n    let n = -2\n    let xs = [1, 2, 3]\n    print(xs[n:].len())\n}\n", "index out of bounds"),
            "a_negative_bound_of_a_string": ("fun main() {\n    let t = \"abc\"\n    print(t[:-1:-1])\n}\n", "index out of bounds"),
        }
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (src, want) in cases.items():
                path = os.path.join(tmp, name + ".my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(src)
                exe = os.path.join(tmp, name)
                subprocess.run([myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT, *target_flags()], check=True)
                for runner, argv in (("interpreter", [myla, "run", path, "--stdlib", STDLIB_ROOT]),
                                     ("native", run_argv(exe, exe)[0])):
                    with self.subTest(case=name, runner=runner):
                        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
                        self.assertEqual((proc.stdout, proc.returncode), ("", 1), proc.stderr)
                        self.assertIn("runtime error: ", proc.stderr)
                        self.assertIn(want, proc.stderr)
                        self.assertIn(f"{name}.my:", proc.stderr)

    def test_type_errors(self):
        cases = {
            "a_map": ("fun main() {\n    let m = [1: 2]\n    print(m[1:2].len())\n}\n", "a map has no slices"),
            "caret_outside": ("fun main() {\n    let n = ^1\n}\n", "'^' counts from the end only in an index or a slice's bound"),
            "caret_step": ("fun main() {\n    let xs = [1]\n    print(xs[::^1].len())\n}\n", "a slice's step is a plain integer"),
            "assign_to_a_slice": ("fun main() {\n    var xs = [1, 2]\n    xs[0:1] = [3]\n}\n", "a slice can't be assigned to"),
            "a_float_bound": ("fun main() {\n    let xs = [1]\n    print(xs[0.5:].len())\n}\n", "a slice's bounds and step are integers"),
        }
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (src, want) in cases.items():
                with self.subTest(case=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(src)
                    proc = subprocess.run([myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                                          text=True)
                    self.assertEqual(proc.returncode, 1, proc.stderr)
                    self.assertIn("error: " + want, proc.stderr)


if __name__ == "__main__":
    unittest.main()
