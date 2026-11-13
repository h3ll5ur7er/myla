"""Burn test: a function's labels are its own (MYLA-552).

The labels of the blocks and branches of a function, of the positions its
runtime errors report and of the string literals and float constants it uses
are named by the function, the text or the bits, not by a count over the whole
program (`CodeGen.begin_labels`, `str_name`, `fconst_label`). A change in one
function, here a branch and a string literal more, then renames no other
function's labels, so a new seed differs from the last only where the
compiler changed (the seeds' updates cost the repository's history 2.9 MB
each with the labels counted over the program, review 2026-11-12).
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest

from ._tools import STDLIB_ROOT, selfhost_tool

PROGRAM = """fun first(n: int) -> str {
    if n > 3 {
        return "big"
    }
    return "small"
}

fun second(xs: [int]) -> int {
    var total = 0
    for x in xs {
        if x % 2 == 0 { total += x } else { total -= 1 }
    }
    return total + xs[1]
}

fun third(s: str) -> float {
    var f = 0.5
    if s == "small" { f = 2.5 }
    return f * 1.5
}

fun main() {
    print(first(4))
    print(second([1, 2, 3, 4]))
    print(third(first(1)))
}
"""

# `first` with a branch, a string literal and a runtime error's position more
CHANGED = PROGRAM.replace('''    if n > 3 {
        return "big"
    }''', '''    if n > 3 {
        return "big"
    }
    if n == 2 {
        return "two"
    }
    let ys = [n]
    if ys[n] == 7 {
        return "seven"
    }''')


def functions(asm: str) -> dict[str, str]:
    """Each function's text, by its symbol (`myla_second:` to the empty line
    after it)."""
    out: dict[str, str] = {}
    name = ""
    lines: list[str] = []
    for line in asm.split("\n"):
        m = re.match(r"(myla_[^:\s]+):$", line)
        if m:
            name, lines = m.group(1), []
        elif name and line == "":
            out[name] = "\n".join(lines)
            name = ""
        elif name:
            lines.append(line)
    return out


class LabelsPerFunction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gen = selfhost_tool("gen_main")
        cls._tmp = tempfile.TemporaryDirectory(prefix="myla_labels_")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def assembly(self, text: str, target: str) -> str:
        path = os.path.join(self._tmp.name, "p.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return subprocess.run([self.gen, path, STDLIB_ROOT, "--target", target], capture_output=True, text=True,
                              check=True, timeout=600).stdout

    def test_a_change_in_one_function_renames_no_other_label(self) -> None:
        for target in ("x86_64-linux", "aarch64-linux"):
            with self.subTest(target=target):
                before = functions(self.assembly(PROGRAM, target))
                after = functions(self.assembly(CHANGED, target))
                self.assertIn("myla_first", before)
                self.assertNotEqual(before["myla_first"], after["myla_first"])
                changed = [n for n in before if n != "myla_first" and before[n] != after.get(n)]
                self.assertEqual(changed, [])

    def test_the_labels_are_named_by_their_function(self) -> None:
        # by the function's own (mangled) name, for a reader of the assembly
        # (D196): `.Lsecond_3`, `.Lsecond_ret`
        asm = self.assembly(PROGRAM, "x86_64-linux")
        for name in ("first", "second", "third"):
            body = functions(asm)["myla_" + name]
            labels = set(re.findall(r"^(\.L[^\s:]+):$", body, re.M))
            self.assertIn(f".L{name}_1", labels, body)
            self.assertIn(f".L{name}_ret", labels, body)
            for lab in labels:
                self.assertRegex(lab, rf"^\.L{name}_(\d+|p\d+|ret)$", body)
        # a string literal by its text, a float constant by its bits
        self.assertRegex(asm, r"\.Lstr[0-9a-z]{7}:")
        self.assertRegex(asm, r"\.Lfc3ff8000000000000:\n\t\.quad 4609434218613702656\n")   # 1.5

if __name__ == "__main__":
    unittest.main()
