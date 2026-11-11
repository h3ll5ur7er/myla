"""Burn test: the standard library's bodies read once called (D179, MYLA-432).

The lowering and the back ends call some functions of `std` by their mangled
names (`std$fmt$fmt_int` for an f-string's hole, `std$slice$take` for a
slice, the runtime's), where no code the checker checks calls them. The
checker marks those on `backend_std_functions` (`selfhost/checker.my`) as
called, so that a body the loader left unread is always read for them, and a
build that asks for another function of `std` nobody called is an internal
error (`Checker.unmarked_std`). The list is checked here against the names
the back ends' sources write.
"""
from __future__ import annotations

import os
import re
import unittest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_SELFHOST = os.path.join(_REPO, "selfhost")

# the lowering, the back ends and what they share: the files that may name a
# function of `std` to call
BACK_END_FILES = ["lower.my", "codegen.my", "ir.my", "ir_util.my", "ir_x86.my", "ir_a64.my", "ir_wasm.my",
                  "runtime_x86.my", "runtime_a64.my", "runtime_wasm.my", "inline.my", "ownership.my",
                  "anf.my", "hoist.my", "ranges.my", "ssa.my", "dwarf.my"]


def listed_names() -> set[str]:
    """The names of `backend_std_functions` in `selfhost/checker.my`."""
    with open(os.path.join(_SELFHOST, "checker.my"), encoding="utf-8") as fh:
        src = fh.read()
    start = src.index("pub fun backend_std_functions() -> [str] {")
    body = src[start:src.index("\n}\n", start)]
    return set(re.findall(r'"(std\$[a-z_0-9]+\$[A-Za-z_][A-Za-z_0-9]*)"', body))


def named_by(path: str) -> dict[str, int]:
    """The functions of `std` the file `path` names (outside its comments and
    `#test` cases), each with the first line that does: a mangled name in a
    string (`"std$rt$alloc"`, `"bl myla_std$rt$fmod"`) or std.platform's by
    `platform_fn("…")`."""
    out: dict[str, int] = {}
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            text = line.strip()
            if text.startswith("//") or text.startswith("#test"):
                continue
            for s in re.findall(r'"[^"\n]*"', line):
                for name in re.findall(r"std\$[a-z_0-9]+\$[A-Za-z_][A-Za-z_0-9]*", s):
                    out.setdefault(name, n)
            for name in re.findall(r'platform_fn\("([a-z_0-9]+)"\)', line):
                out.setdefault("std$platform$" + name, n)
    return out


class BackEndNames(unittest.TestCase):
    def test_every_name_a_back_end_writes_is_listed(self) -> None:
        listed = listed_names()
        self.assertGreater(len(listed), 50)
        missing = []
        seen: set[str] = set()
        for f in BACK_END_FILES:
            for name, line in named_by(os.path.join(_SELFHOST, f)).items():
                seen.add(name)
                if name not in listed:
                    missing.append(f"selfhost/{f}:{line}: {name}")
        self.assertEqual(missing, [], "add these to backend_std_functions in selfhost/checker.my")
        # and nothing on the list that no back end names any more
        self.assertEqual(sorted(listed - seen), [])

    def test_the_scan_finds_a_name(self) -> None:
        # the scan itself: a name in a string, not one in a comment or a case
        path = os.path.join(_SELFHOST, "lower.my")
        names = named_by(path)
        self.assertIn("std$fmt$fmt_int", names)
        self.assertIn("std$slice$take", names)
        self.assertNotIn("std$list$sum", names)  # only in a `#test` case of `checked_code`


if __name__ == "__main__":
    unittest.main()
