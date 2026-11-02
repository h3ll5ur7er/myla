"""Burn test: maps iterate in insertion order (D105, MYLA-179).

`for k in m` and `keys(m)` visit the keys in the order they were first
inserted, in the self-hosted interpreter and in native code alike: replacing
a value keeps its key's place, removing a key and inserting it again moves it
to the end, and the order survives the table growing (several times here) and
the rebuild after each removal."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, selfhost_run
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """fun show(m: [int: int]) -> str {
    var sb = StringBuilder()
    for k in m {
        append(sb, f"{k}={m[k]} ")
    }
    return build(sb)
}

fun main() {
    // keys in a scrambled order, through several grows
    var m: [int: int] = [:]
    var x = 7
    for i in 0..300 {
        x = (x * 37 + 11) % 1013
        m[x] = i
    }
    // replacing keeps the place; removing and inserting again moves to the end
    m[x] = -1
    let ks = keys(m)
    remove(m, ks[0])
    remove(m, ks[5])
    remove(m, ks[100])
    m[ks[5]] = 5000
    var line = ""
    for k in keys(m) {
        line = line + f"{k} "
    }
    print(line)
    print(show(m))
    print(len(m))
    // string keys, a value that owns heap cells
    var w: [str: [str]] = ["pear": ["p"], "apple": ["a"], "fig": []]
    w["banana"] = ["b", "bb"]
    remove(w, "apple")
    w["apple"] = ["again"]
    w["pear"] = ["pp"]
    for k in w {
        print(f"{k} {len(w[k])}")
    }
    // a copy keeps the order and goes its own way
    var c = w
    remove(c, "fig")
    c["fig"] = ["last"]
    print(join_keys(keys(w)))
    print(join_keys(keys(c)))
}

fun join_keys(ks: [str]) -> str {
    var s = ""
    for k in ks {
        s = s + k + ","
    }
    return s
}
"""


def _expected() -> str:
    m: dict[int, int] = {}
    x = 7
    for i in range(300):
        x = (x * 37 + 11) % 1013
        m[x] = i
    m[x] = -1
    ks = list(m)
    for k in (ks[0], ks[5], ks[100]):
        del m[k]
    m[ks[5]] = 5000
    out = ["".join(f"{k} " for k in m), "".join(f"{k}={v} " for k, v in m.items()), str(len(m))]
    w = {"pear": ["p"], "apple": ["a"], "fig": []}
    w["banana"] = ["b", "bb"]
    del w["apple"]
    w["apple"] = ["again"]
    w["pear"] = ["pp"]
    out += [f"{k} {len(v)}" for k, v in w.items()]
    c = dict(w)
    del c["fig"]
    c["fig"] = ["last"]
    out += ["".join(k + "," for k in w), "".join(k + "," for k in c)]
    return "\n".join(out) + "\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class MapOrder(unittest.TestCase):
    def test_insertion_order_in_the_interpreter_and_natively(self):
        want = _expected()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "order.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_PROGRAM)
            self.assertEqual(selfhost_run(path), (want, "", 0))
            exe = os.path.join(tmp, "order")
            subprocess.run([selfhost_tool("main"), "build", path, "-o", exe, "--stdlib", STDLIB_ROOT],
                           check=True, capture_output=True)
            proc = subprocess.run([exe], capture_output=True, text=True, timeout=60)
            self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (want, "", 0))


if __name__ == "__main__":
    unittest.main()
