"""Burn test: `m.get(k)`, std.map's lookup (MYLA-393).

The prelude's free `get(m, k)` went for a method of `std.map` (implicit,
D164): `m.get(k)` is `Some` of the value of `k`, or `None` when the map has
no `k`. Keys of every kind a map takes (D163) are looked up, an integer, a
string, a tuple and a `#derive(Eq, Hash)` struct, in the self-hosted
interpreter and natively alike; a value that owns heap cells comes back as
a copy of its own."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, selfhost_run
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """#derive(Eq, Hash)
struct Pos {
    x: int,
    y: int,
}

fun shown(o: Option<int>) -> str {
    return match o {
        Some(v) => f"Some({v})"
        None => "None"
    }
}

fun main() {
    var by_int: [int: int] = [:]
    for i in 0..100 {
        by_int[i * 7] = i
    }
    print(shown(by_int.get(49)))
    print(shown(by_int.get(50)))
    let by_str = ["one": 1, "two": 2]
    print(shown(by_str.get("two")))
    print(shown(by_str.get("three")))
    let by_pair: [(int, str): int] = [(1, "a"): 10, (2, "b"): 20]
    print(shown(by_pair.get((2, "b"))))
    print(shown(by_pair.get((2, "a"))))
    var by_pos: [Pos: int] = [:]
    by_pos[Pos { x: 3, y: 4 }] = 5
    print(shown(by_pos.get(Pos { x: 3, y: 4 })))
    print(shown(by_pos.get(Pos { x: 4, y: 3 })))
    let empty: [str: int] = [:]
    print(shown(empty.get("")))
    // a value that owns heap cells: the copy goes its own way
    var lists: [str: [int]] = ["xs": [1, 2]]
    if let Some(xs) = lists.get("xs") {
        var mine = xs
        mine.push(3)
        print(f"{mine.len()} {lists["xs"].len()}")
    }
    // a removed key is gone, one written again is back
    var m = by_str
    m.remove("one")
    print(shown(m.get("one")))
    m["one"] = 11
    print(shown(m.get("one")))
    print(m.get("two").unwrap_or(0) + m.get("nine").unwrap_or(-1))
}
"""

_OUTPUT = """Some(7)
None
Some(2)
None
Some(20)
None
Some(5)
None
None
3 2
None
Some(11)
1
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class MapGet(unittest.TestCase):
    def test_get_in_the_interpreter_and_natively(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "get.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_PROGRAM)
            self.assertEqual(selfhost_run(path), (_OUTPUT, "", 0))
            exe = os.path.join(tmp, "get")
            built = subprocess.run([selfhost_tool("main"), "build", path, "-o", exe, "--stdlib", STDLIB_ROOT],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            proc = subprocess.run([exe], capture_output=True, text=True, timeout=60)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_OUTPUT, "", 0))


if __name__ == "__main__":
    unittest.main()
