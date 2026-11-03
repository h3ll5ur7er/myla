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


if __name__ == "__main__":
    unittest.main()
