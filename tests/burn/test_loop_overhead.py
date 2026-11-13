"""Burn test: less overhead in loops and branches (MYLA-251).

- A negated flag that only a branch reads is the inverted jump, not a 0/1
  value made with `sete`/`movzbq` and tested.
- The last block falls into the epilogue instead of jumping to the label
  right after it.
- A copy-on-write check takes the list's address straight into the register
  it works on.
Programs that branch on negated flags (from lists, calls, comparisons) print
the same natively and interpreted."""
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import _REPO, STDLIB_ROOT, selfhost_tool

_PROGRAM = """fun odd(n: int) -> bool {
    return n % 2 == 1
}

fun fib(n: int) -> int {
    if n < 2 {
        return n
    }
    return fib(n - 1) + fib(n - 2)
}

fun main() {
    var flags: [bool] = []
    for i in 0..20 {
        flags.push(i % 3 == 0)
    }
    var a = 0
    var b = 0
    for i in 0..20 {
        if !flags[i] { a += 1 }
        if !odd(i) { b += i }
        let big = i > 10
        if !big { b += 100 }
        if !(flags[i] && odd(i)) { a += 1000 }
    }
    print(a)
    print(b)
    print(fib(15))
}
"""


def _function(asm: str, name: str) -> str:
    m = re.search(rf"^myla_{name}:\n(.*?)(?=^myla_\w+:|\Z)", asm, re.S | re.M)
    if not m:
        raise AssertionError(f"no function {name}")
    return m.group(1)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class LoopOverhead(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "flags.my")
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(_PROGRAM)

    def asm(self, path: str) -> str:
        return subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT], capture_output=True, text=True,
                              check=True).stdout

    def test_a_negated_flag_branches_directly(self):
        body = _function(self.asm(os.path.join(_REPO, "benchmarks", "sieve", "sieve.my")), "count_primes")
        self.assertNotIn("sete", body)

    def test_the_last_block_falls_into_the_epilogue(self):
        body = _function(self.asm(self.path), "fib")
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        for prev, line in zip(lines, lines[1:]):
            if line.endswith(":") and prev.startswith("jmp "):
                self.assertNotEqual(prev, "jmp " + line[:-1], "a jump to the next line")

    def test_branches_on_negated_flags_print_the_same(self):
        myla = selfhost_tool("main")
        ran = subprocess.run([myla, "run", self.path], capture_output=True, text=True)
        self.assertEqual((ran.stdout, ran.returncode), ("17013\n1190\n610\n", 0), ran.stderr)
        exe = os.path.join(self.tmp.name, "flags")
        built = subprocess.run([myla, "build", self.path, "-o", exe], capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(subprocess.run([exe], capture_output=True, text=True).stdout, ran.stdout)

    def test_the_copy_on_write_check_is_made_before_the_loop(self):
        # MYLA-251: `composite[j] = true` in the sieve's inner loop checks
        # once, before the loop, that the list is held once; the loop itself
        # calls no copy
        body = _function(self.asm(os.path.join(_REPO, "benchmarks", "sieve", "sieve.my")), "count_primes")
        store = body.index("movb $1, ")
        back = re.compile(r"\n\tj(?:l|ge|ne|e|b|ae|g|le) (\.L[^\s:]+_\d+)\n").search(body, store).group(1)
        loop = body[body.index("\n" + back + ":\n"):body.index(back + "\n", store)]
        self.assertIn("movb $1, ", loop)
        self.assertNotIn("__clone_list", loop, loop)

    def test_copies_on_write_around_loops_print_the_same(self):
        # a list shared before the loop is still copied (once); a loop that
        # shares it again, calls something or puts another list in its place
        # keeps the check where it was
        path = os.path.join(self.tmp.name, "cow.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_COW_LOOPS)
        myla = selfhost_tool("main")
        ran = subprocess.run([myla, "run", path], capture_output=True, text=True)
        self.assertEqual((ran.stdout, ran.returncode), (_COW_WANT, 0), ran.stderr)
        exe = os.path.join(self.tmp.name, "cow")
        built = subprocess.run([myla, "build", path, "-o", exe], capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(subprocess.run([exe], capture_output=True, text=True).stdout, ran.stdout)

    def test_a_counting_loops_increment_is_not_re_extended(self):
        # MYLA-251: `i + 1` where `i < n` held (n an int32) can't overflow, so
        # it is a 64-bit add, with no sign extension after it
        path = os.path.join(self.tmp.name, "count.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_COUNTING)
        body = _function(self.asm(path), "total")
        self.assertRegex(body, r"addq \$1, %r\w+\n")
        self.assertNotRegex(body, r"addq \$1, (%r\w+)\n\tmovslq %\w+, \1\n", body)

    def test_a_remainder_and_a_sum_before_it_are_not_re_extended(self):
        # MYLA-251: a remainder is in its operands' range already, and `y + n`
        # re-extended just before `- 1` overwrites the register was moot
        path = os.path.join(self.tmp.name, "wrapped.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_WRAPPED)
        body = _function(self.asm(path), "wrapped")
        self.assertIn("idivq", body, body)
        self.assertNotRegex(body, r"movq %rdx, %rax\n(\.L[^\s:]+_\d+:\n)?\tmovslq", body)
        self.assertNotRegex(body, r"movslq %(\w+), %\w+\n\tleal [^\n]*, %\1\n", body)

    def test_integer_operations_at_the_limits_print_the_same(self):
        # every operation whose result no longer re-extends, at its type's
        # limits: natively as interpreted, the wrapping ones through the
        # wrapping methods (D175), which a plain build lowers as the operators
        path = os.path.join(self.tmp.name, "wide.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_WIDE_LIMITS)
        myla = selfhost_tool("main")
        ran = subprocess.run([myla, "run", path], capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(len(ran.stdout.splitlines()), 237)
        exe = os.path.join(self.tmp.name, "wide")
        built = subprocess.run([myla, "build", path, "-o", exe], capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(subprocess.run([exe], capture_output=True, text=True).stdout, ran.stdout)

    def test_counting_loops_at_the_limit_print_the_same(self):
        # at INT32_MAX: a `<` loop ends there; a `<=` loop's increment wraps,
        # as it must (written with `wrapping_add`, D175), and a loop that
        # changes its counter elsewhere too stays as it was
        path = os.path.join(self.tmp.name, "limit.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_LIMITS)
        myla = selfhost_tool("main")
        ran = subprocess.run([myla, "run", path], capture_output=True, text=True)
        self.assertEqual((ran.stdout, ran.returncode), (_LIMITS_WANT, 0), ran.stderr)
        exe = os.path.join(self.tmp.name, "limit")
        built = subprocess.run([myla, "build", path, "-o", exe], capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(subprocess.run([exe], capture_output=True, text=True).stdout, ran.stdout)


_WRAPPED = """fun wrapped(ys: [int], n: int) -> int {
    var t = 0
    for y in ys {
        t += (y + n - 1) % n
    }
    return t
}

fun main() {
    print(wrapped([3, -6, 4], 5))
}
"""

_WIDE_LIMITS = """// Integer operations at their types' limits (MYLA-251): the same natively
// as interpreted, wrapping through the wrapping methods (D175), the plain
// operators natively.
fun signed32(xs: [int]) {
    for a in xs {
        for b in xs {
            // the minimum by -1 overflows where it is checked (D175)
            if b != 0 && !(a == -2147483647 - 1 && b == -1) { print(f"{a / b} {a % b}") }
            print(f"{a & b} {a | b} {a ^ b} {a >> 3} {a >> 31} {a.wrapping_add(b).wrapping_sub(1)} {a.wrapping_sub(b).wrapping_mul(3).wrapping_add(1)} {a.wrapping_add(b) % 7}")
        }
    }
}

fun unsigned32(xs: [uint32]) {
    for a in xs {
        for b in xs {
            if b != 0u32 { print(f"{a / b} {a % b}") }
            print(f"{a & b} {a | b} {a ^ b} {a >> 3u32} {a.wrapping_add(b).wrapping_sub(1u32)} {a / 8u32} {a % 8u32}")
        }
    }
}

fun small(xs: [int8], ys: [uint8], zs: [int16]) {
    for a in xs {
        for b in xs {
            if b != 0i8 && !(a == -128i8 && b == -1i8) { print(f"{a / b} {a % b}") }
            print(f"{a & b} {a | b} {a ^ b} {a >> 2i8} {a.wrapping_add(b)}")
        }
    }
    for a in ys {
        for b in ys {
            if b != 0u8 { print(f"{a / b} {a % b}") }
            print(f"{a & b} {a | b} {a ^ b} {a >> 2u8} {a.wrapping_add(b)}")
        }
    }
    for a in zs {
        for b in zs {
            if b != 0i16 && !(a == -32768i16 && b == -1i16) { print(f"{a / b} {a % b}") }
            print(f"{a ^ b} {a >> 15i16} {a.wrapping_sub(b)}")
        }
    }
}

// constants as the second operand
fun f(a: uint32, b: int32, c: uint8, d: int64) -> int64 {
    let x = a ^ 4294967295u32
    let y = a & 4294967295u32
    let z = a | 2147483648u32
    let w = b ^ -1
    let v = b & -2147483648
    let u = c ^ 255u8
    let t = c | 128u8
    let s = a >> 31u32
    let r = b >> 31
    print(f"{x} {y} {z} {w} {v} {u} {t} {s} {r}")
    print(x > 5u32 && z > 5u32)
    return x as int64 + y as int64 + z as int64 + w as int64 + v as int64 + u as int64 + t as int64 + d
}
fun main() {
    let mn = -2147483647 - 1
    signed32([mn, -7, -1, 0, 1, 7, 2147483647])
    unsigned32([0u32, 1u32, 7u32, 2147483648u32, 4294967295u32])
    small([-128i8, -1i8, 3i8, 127i8], [0u8, 1u8, 200u8, 255u8], [-32768i16, -3i16, 5i16, 32767i16])
    // `mn / -1` overflows where it is checked (test_ir_contract has a plain
    // build's); its remainder fits
    print(mn.wrapping_neg())
    print(mn % -1)
    print(f(7u32, 7, 7u8, 1))
    print(f(4294967295u32, -2147483648, 255u8, 2))
    print(f(0u32, 2147483647, 0u8, 3))
}
"""

_COUNTING = """fun total(xs: [int], n: int) -> int {
    var t = 0
    for i in 0..n {
        t += xs[i]
    }
    return t
}

fun main() {
    print(total([1, 2, 3], 3))
}
"""

_LIMITS = """fun main() {
    var i = 2147483640
    while i < 2147483647 {
        i += 1
    }
    print(i)
    var j = 2147483646
    var turns = 0
    while j <= 2147483647 {
        j = j.wrapping_add(1)
        turns += 1
        if turns > 3 {
            break
        }
    }
    print(j)
    var k = 2147483646
    var kt = 0
    while k < 2147483647 {
        k += 1
        k = k.wrapping_add(1)
        kt += 1
        if kt > 1 {
            break
        }
    }
    print(k)
    var m: int = 0
    for x in 2147483645..2147483647 {
        m = x + 1
    }
    print(m)
}
"""

_LIMITS_WANT = "2147483647\n-2147483646\n-2147483646\n2147483647\n"


_COW_LOOPS = """fun total(xs: [int]) -> int {
    var t = 0
    for x in xs {
        t += x
    }
    return t
}

fun main() {
    // shared before the loop: the loop's writes go to a copy
    let kept = [1, 2, 3, 4]
    var xs = kept
    var i = 0
    while i < 4 {
        xs[i] = xs[i] * 10
        i += 1
    }
    print(total(kept))
    print(total(xs))
    // shared again in the loop: each turn's writes go to a copy of that turn
    var ys = [1, 1, 1]
    var olds: [[int]] = []
    var j = 0
    while j < 3 {
        olds.push(ys)
        ys[j] = 5
        j += 1
    }
    print(total(olds[0]))
    print(total(olds[2]))
    print(total(ys))
    // shared with another variable in the loop
    var zs = [0, 0]
    var keep: [int] = []
    var k = 0
    while k < 2 {
        zs[k] = k + 7
        keep = zs
        k += 1
    }
    zs[0] = 100
    print(total(keep))
    print(total(zs))
    // another list put in its place in the loop
    var ws = [1, 2]
    var m = 0
    while m < 3 {
        ws[0] = m
        ws = [ws[0] + 10, ws[1]]
        m += 1
    }
    print(ws[0])
    print(ws[1])
}
"""

_COW_WANT = "10\n100\n3\n11\n15\n15\n108\n12\n2\n"


if __name__ == "__main__":
    unittest.main()
