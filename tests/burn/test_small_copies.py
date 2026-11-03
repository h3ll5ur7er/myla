"""Burn test: small values are copied with moves, not `rep movsq` (MYLA-246).

The native backend copies a struct, tuple or enum value word by word with
`movq` up to 8 words, and with `rep movsq` only above that: the string
instruction starts slowly (tens of cycles for three words), which made the
binary-trees benchmark six times slower than C (MYLA-242). The values copied
either way come out the same."""
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """enum Tree {
    Leaf,
    Node(Tree, Tree),
}

struct Small {
    a: int,
    b: int64,
    c: str,
}

struct Big {
    a: int64, b: int64, c: int64, d: int64, e: int64,
    f: int64, g: int64, h: int64, i: int64,
}

fun check(t: Tree) -> int {
    return match t {
        Tree.Leaf => 0,
        Tree.Node(l, r) => 1 + check(l) + check(r),
    }
}

fun small_sum(s: Small) -> int64 {
    let copy = s
    return copy.b + (copy.a as int64) + (copy.c.len() as int64)
}

fun big_sum(x: Big) -> int64 {
    let copy = x
    return copy.a + copy.e + copy.i
}

fun main() {
    let t = Tree.Node(Tree.Node(Tree.Leaf, Tree.Leaf), Tree.Node(Tree.Leaf, Tree.Leaf))
    print(check(t))
    print(small_sum(Small { a: 1, b: 2, c: "abc" }))
    print(big_sum(Big { a: 1, b: 2, c: 3, d: 4, e: 5, f: 6, g: 7, h: 8, i: 9 }))
}
"""

_WANT = "3\n6\n15\n"


def _function(asm: str, name: str) -> str:
    """The assembly of the user function `name`: from its label to the next
    function's."""
    m = re.search(rf"^myla_{name}:\n(.*?)(?=^myla_\w+:|\Z)", asm, re.S | re.M)
    if not m:
        raise AssertionError(f"no function {name} in the assembly")
    return m.group(1)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class SmallCopies(unittest.TestCase):
    def test_small_values_are_moved_and_big_ones_copied_as_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "copies.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_PROGRAM)
            asm = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT], capture_output=True, text=True,
                                 check=True).stdout
            for name in ("check", "small_sum"):
                with self.subTest(function=name):
                    self.assertNotIn("rep movsq", _function(asm, name))
            self.assertIn("rep movsq", _function(asm, "big_sum"))
            myla = selfhost_tool("main")
            exe = os.path.join(tmp, "copies")
            built = subprocess.run([myla, "build", path, "-o", exe], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertEqual(subprocess.run([exe], capture_output=True, text=True).stdout, _WANT)
            ran = subprocess.run([myla, "run", path], capture_output=True, text=True)
            self.assertEqual(ran.stdout, _WANT)


if __name__ == "__main__":
    unittest.main()
