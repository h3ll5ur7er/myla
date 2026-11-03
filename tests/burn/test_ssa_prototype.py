"""Burn test: D123's prototype, the scalar slots promoted to values
(`gen_main --ssa`, MYLA-254).

Programs with loops, joins, swaps between loop variables, parameters read
at once, early returns, function values, tasks and every list width print
the same natively with the slots promoted as the interpreter prints; the
statistics name what went, and the promoted IR reads no promoted slot."""
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool
from tests.burn.test_packed_lists import _PROGRAM as BOOLS, _WIDTHS as WIDTHS
from tests.burn.test_register_args import ASYNC as CALLS

_LOOPS = """struct Out {
    data: [int],
    code: int,
}

fun fetch(n: int) -> Result<Out, str> {
    if n > 0 {
        return Ok(Out { data: [1, 2, 3], code: n })
    }
    return Err("no")
}

// two loop variables swapped every turn: the joins' copies are parallel
fun fib(n: int) -> int64 {
    var a: int64 = 0
    var b: int64 = 1
    var i = 0
    while i < n {
        let t = a + b
        a = b
        b = t
        i += 1
    }
    return a
}

fun collatz(start: int64) -> int {
    var x = start
    var steps = 0
    while x != 1 {
        if x % 2 == 0 {
            x = x / 2
        } else {
            x = 3 * x + 1
        }
        steps += 1
    }
    return steps
}

fun first_over(xs: [int], limit: int) -> int {
    var found = -1
    for x in xs {
        if x > limit && found < 0 {
            found = x
        }
    }
    return found
}

fun main() {
    print(fib(90))
    var most = 0
    var at: int64 = 0
    var s: int64 = 1
    while s < 3000 {
        let c = collatz(s)
        if c > most {
            most = c
            at = s
        }
        s += 1
    }
    print(at)
    print(most)
    print(first_over([3, 9, 27, 81], 10))
    print(first_over([1, 2], 10))
    match fetch(2) {
        Ok(out) => {
            print(out.data.len())
            print(out.code)
        },
        Err(e) => { print(e) },
    }
    let flag = true
    var n = 0
    while flag && n < 5 {
        n += 1
    }
    print(n)
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class SsaPrototype(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def promoted(self, name: str, text: str) -> str:
        path = os.path.join(self.tmp.name, name + ".my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        ran = subprocess.run([selfhost_tool("main"), "run", path], capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        gen = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT, "--ssa-stats"], capture_output=True,
                             text=True)
        self.assertEqual(gen.returncode, 0, gen.stderr)
        stats = gen.stderr.strip().splitlines()[-1]
        m = re.match(r"ssa: (\d+) of (\d+) slots promoted; (\d+) loads and (\d+) stores removed", stats)
        self.assertTrue(m, stats)
        self.assertGreater(int(m.group(1)), 0, stats)
        asm = os.path.join(self.tmp.name, name + ".s")
        with open(asm, "w", encoding="utf-8") as fh:
            fh.write(gen.stdout)
        obj, exe = asm[:-2] + ".o", asm[:-2]
        subprocess.run(["as", "--64", "-o", obj, asm], check=True)
        subprocess.run(["ld", "-o", exe, obj], check=True)
        native = subprocess.run([exe], capture_output=True, text=True)
        self.assertEqual((native.stdout, native.returncode), (ran.stdout, 0), native.stderr)
        return path

    def test_loops_and_joins_print_the_same(self):
        path = self.promoted("loops", _LOOPS)
        ir = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT, "--emit-ir", "--ssa"],
                            capture_output=True, text=True, check=True).stdout
        fib = re.search(r"^fun myla_fib .*?^}", ir, re.S | re.M).group(0)
        # a, b, i and t ($1 to $4) are values now: no slot of theirs is read
        # or written (the parameter n is read once, at the entry)
        self.assertNotRegex(fib, r"(load|store) \$[1-4]\b")
        self.assertRegex(fib, r"%t\d+ = %t\d+")

    def test_calls_print_the_same(self):
        self.promoted("calls", CALLS)

    def test_lists_print_the_same(self):
        self.promoted("bools", BOOLS)
        self.promoted("widths", WIDTHS)


if __name__ == "__main__":
    unittest.main()
