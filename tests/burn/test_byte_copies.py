"""Burn test: short byte copies without `rep movsb` (MYLA-252).

The runtime copies a string's or list's bytes 8 at a time, then the tail,
and only a long copy (512 bytes and up) with `rep movsb`, whose start costs
tens of cycles. Concatenation, builders, number formatting and list clones
of every length around the edges (0 to 40 bytes, and across 512) give the
same natively and interpreted."""
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import selfhost_tool

_PROGRAM = """fun piece(n: int) -> str {
    var sb = StringBuilder()
    for i in 0..n {
        sb.append_byte((97 + i % 26) as uint8)
    }
    return sb.build()
}

fun checksum(s: str) -> int64 {
    var h: int64 = 0
    for i in 0..s.len() {
        h = (h * 31 + (s[i] as int64)) % 1000000007
    }
    return h
}

fun main() {
    var total: int64 = 0
    let lengths = [0, 1, 2, 3, 7, 8, 9, 15, 16, 17, 23, 24, 25, 31, 32, 33, 40, 255, 511, 512, 513, 1000, 2049]
    for a in lengths {
        for b in [0, 1, 8, 9, 513] {
            let s = piece(a) + piece(b)
            total += (s.len() as int64) * 7 + checksum(s)
            var sb = StringBuilder()
            sb.append(piece(a))
            sb.append(f"{a}-{b}")
            sb.append(piece(b), 0, b)
            total += checksum(sb.build())
        }
        var xs: [int] = []
        for i in 0..a {
            xs.push(i * 3)
        }
        var ys = xs
        if a > 0 {
            ys[0] = 99
        }
        total += (ys.len() as int64) + (if a > 0 { (xs[0] + ys[0]) as int64 } else { 0 })
    }
    print(total)
    print(format("{} {} {}", 0, 9876543210u64, 18446744073709551615u64))
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class ByteCopies(unittest.TestCase):
    def test_copies_of_every_length_print_the_same(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "copies.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_PROGRAM)
            myla = selfhost_tool("main")
            ran = subprocess.run([myla, "run", path], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)
            exe = os.path.join(tmp, "copies")
            built = subprocess.run([myla, "build", path, "-o", exe], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertEqual(subprocess.run([exe], capture_output=True, text=True).stdout, ran.stdout)
            self.assertIn("0 9876543210 18446744073709551615", ran.stdout)
            asm = subprocess.run([selfhost_tool("gen_main"), path], capture_output=True, text=True, check=True).stdout
            concat = re.search(r"^__str_concat:\n(.*?)^\s*ret$", asm, re.S | re.M).group(1)
            self.assertIn("cmpq $512, %rcx", concat)


if __name__ == "__main__":
    unittest.main()
