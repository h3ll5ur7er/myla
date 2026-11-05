"""Burn test: `impl` blocks on builtin types (D103, MYLA-221).

A program can give lists, maps, `char` and the float types methods of its
own, generic ones included (`impl<T> [T]`), as it can structs, `str` and the
integer types. A list's or map's methods are keyed by the kind of type, as a
generic struct's are by its name. The self-hosted interpreter and native code
agree."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_source_both_now
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

PROGRAM = """impl [int] {
    fun total(self) -> int {
        var t = 0
        for x in self {
            t += x
        }
        return t
    }
}

impl<T> [T] {
    fun second(self) -> T {
        return self[1]
    }

    fun count_if(self, f: (T) -> bool) -> int {
        var n = 0
        for x in self {
            if f(x) {
                n += 1
            }
        }
        return n
    }
}

impl [str: int] {
    fun sum_values(self) -> int {
        var t = 0
        for k in self {
            t += self[k]
        }
        return t
    }
}

impl<K, V> [K: V] {
    fun size(self) -> int {
        return self.len()
    }
}

impl char {
    fun is_vowel(self) -> bool {
        return self == 'a' || self == 'e' || self == 'i' || self == 'o' || self == 'u'
    }
}

impl float64 {
    fun half(self) -> float64 {
        return self / 2.0
    }
}

fun main() {
    let xs = [1, 2, 3]
    print(xs.total())
    print(xs.second())
    print(["a", "b"].second())
    print(xs.count_if((x: int) => x > 1))
    let m = ["a": 1, "b": 2]
    print(m.sum_values())
    print(m.size())
    print([1: true].size())
    print('e'.is_vowel())
    print('z'.is_vowel())
    let f = 3.0
    print(f.half())
    let grid = [[1], [2, 3]]
    print(grid[1].second())
    print(grid.second().total())
}
"""

WANT = "6\n2\nb\n2\n3\n2\n1\ntrue\nfalse\n1.5\n3\n5\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class BuiltinImpls(unittest.TestCase):
    def test_in_the_interpreter_and_natively(self):
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_errors(self):
        cases = {
            "a_var_self_method": ("impl<T> [T] {\n    fun again(var self, x: T) {\n        self.push(x)\n    }\n}\n\n"
                                  "fun main() {\n}\n",
                                  "'var self' methods on built-in types are not supported yet"),
            "the_wrong_element_type": ("impl [int] {\n    fun total(self) -> int {\n        return self.len()\n    }\n}\n\n"
                                       "fun main() {\n    print([\"a\"].total())\n}\n", "type error"),
            "a_method_lists_lack": ("fun main() {\n    let xs = [1]\n    print(xs.nothing())\n}\n", "type error"),
        }
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (src, want) in cases.items():
                with self.subTest(case=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(src)
                    proc = subprocess.run([myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                                          text=True)
                    self.assertEqual(proc.returncode, 1, proc.stderr)
                    self.assertIn(want, proc.stderr)


if __name__ == "__main__":
    unittest.main()
