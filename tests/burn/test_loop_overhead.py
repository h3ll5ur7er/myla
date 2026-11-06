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
        back = re.compile(r"\n\tj(?:l|ge|ne|e|b|ae|g|le) (\.L\d+)\n").search(body, store).group(1)
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
