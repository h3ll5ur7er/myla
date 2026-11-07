"""Burn test: `impl` blocks on builtin types (D103, MYLA-221).

A program can give lists, maps, `char` and the float types methods of its
own, generic ones included (`impl<T> [T]`), as it can structs, `str` and the
integer types. A list's or map's methods are keyed by the kind of type, as a
generic struct's are by its name. A `var self` method of one gets the
address of its caller's place, and `self = v` in it writes the receiver
(D144). The self-hosted interpreter and native code agree."""
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

impl<K: Eq + Hash, V> [K: V] {
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


# `var self` methods on built-in types (D144): on a variable, a field, list
# elements (narrower than a word too) and a map's value; `self = v`, `?`
# leaving early with the receiver written, a `become` passing the receiver
# on, a value shared before the call unchanged in its copy
VAR_SELF = """impl<T> [T] {
    // pushes `x` `n` times, the last by a `become` to itself
    fun push_n(var self, x: T, n: int) {
        if n == 0 {
            return
        }
        self.push(x)
        become self.push_n(x, n - 1)
    }

    fun clear_first(var self) -> bool {
        if self.len() == 0 {
            return false
        }
        var rest: [T] = []
        var i = 1
        while i < self.len() {
            rest.push(self[i])
            i += 1
        }
        self = rest
        return true
    }
}

impl int {
    fun bump(var self, by: int) -> int {
        self = self + by
        return self
    }

    // `?` leaves early with the receiver written already
    fun halve(var self) -> Option<int> {
        self = self / 2
        var odd: Option<int> = Some(self)
        if self % 2 == 1 {
            odd = None
        }
        let v = odd?
        self = self * 10
        return Some(v)
    }
}

impl int8 {
    fun inc(var self) {
        self = self + 1
    }
}

impl str {
    fun shout(var self) {
        self = self + "!"
    }
}

impl bool {
    fun flip(var self) {
        self = !self
    }
}

impl float32 {
    fun double(var self) {
        self = self * 2.0
    }
}

impl<K: Eq + Hash, V> [K: V] {
    fun put_twice(var self, k: K, v: V) {
        self[k] = v
        self[k] = v
    }
}

fun opt(o: Option<int>) -> str {
    return match o {
        Some(v) => f"Some({v})"
        None => "None"
    }
}

fun ints(xs: [int]) -> str {
    var sb = StringBuilder()
    for x in xs { sb.append(f"{x} ") }
    return sb.build()
}

fun strs(xs: [str]) -> str {
    var sb = StringBuilder()
    for x in xs { sb.append(x + " ") }
    return sb.build()
}

struct Box {
    items: [str],
    count: int,
}

impl Box {
    fun add(var self, s: str) {
        self.items.push_n(s, 2)
        let c = self.count.bump(1)
    }
}

fun main() {
    var xs = [1, 2]
    xs.push_n(7, 3)
    print(ints(xs))
    print(xs.clear_first())
    print(ints(xs))
    var empty: [int] = []
    print(empty.clear_first())
    var n = 5
    print(n.bump(15))
    print(n)
    print(opt(n.halve()))
    print(n)
    n = 6
    print(opt(n.halve()))
    print(n)
    var s = "hey"
    s.shout()
    s.shout()
    print(s)
    var b = true
    b.flip()
    print(b)
    // list elements, wide and narrow, and a map's value
    var grid = [[1], [2, 3]]
    grid[1].push_n(4, 2)
    print(f"{ints(grid[0])}| {ints(grid[1])}")
    var small: [int8] = [1, 2, 3]
    small[1].inc()
    small[2].inc()
    print(f"{small[0]} {small[1]} {small[2]}")
    var counts = [10, 20]
    print(counts[1].bump(5))
    print(ints(counts))
    var flags = [false, true]
    flags[0].flip()
    print(f"{flags[0]} {flags[1]}")
    var fs: [float32] = [1.5, 0.25]
    fs[1].double()
    print(f"{fs[0]} {fs[1]}")
    var m = ["a": 1]
    m.put_twice("b", 2)
    let ma = m["a"]
    let mb = m["b"]
    print(f"{m.len()} {ma} {mb}")
    var words = ["x": "hi"]
    words["x"].shout()
    print(words["x"])
    // a field, through a struct's own `var self` method
    var bx = Box { items: [], count: 0 }
    bx.add("q")
    bx.add("r")
    print(strs(bx.items))
    print(bx.count)
    // the receiver's value, shared before the call, isn't changed in its copy
    let before = xs
    xs.push_n(0, 1)
    print(ints(before))
    print(ints(xs))
}
"""

VAR_SELF_WANT = """1 2 7 7 7 
true
2 7 7 7 
false
20
20
Some(10)
100
None
3
hey!!
false
1 | 2 3 4 4 
1 3 4
25
10 25 
true true
1.5 0.5
2 1 2
hi!
q q r r 
2
2 7 7 7 
2 7 7 7 0 
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class BuiltinImpls(unittest.TestCase):
    def test_in_the_interpreter_and_natively(self):
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_var_self_methods(self):
        self.assertEqual(run_source_both_now(VAR_SELF), (VAR_SELF_WANT, "", 0))

    def test_errors(self):
        cases = {
            "an_async_var_self_method": ("impl int {\n    async fun inc(var self) {\n        self = self + 1\n    }\n}\n\n"
                                         "fun main() {\n}\n",
                                         "async 'var self' methods on built-in types are not supported yet"),
            "on_a_let": ("impl int {\n    fun inc(var self) {\n        self = self + 1\n    }\n}\n\n"
                         "fun main() {\n    let n = 1\n    n.inc()\n}\n",
                         "cannot call the mutating method 'inc' on an immutable receiver"),
            "become_on_a_local": ("impl int {\n    fun inc(var self) -> int {\n        self = self + 1\n        return self\n    }\n}\n\n"
                                  "fun f() -> int {\n    var n = 1\n    become n.inc()\n}\n\nfun main() {\n    print(f())\n}\n",
                                  "'become' can call the mutating method 'inc' only on 'self'"),
            "a_struct_reassigning_self": ("struct P {\n    x: int,\n}\n\nimpl P {\n    fun reset(var self) {\n        self = P { x: 0 }\n    }\n}\n\n"
                                          "fun main() {\n}\n", "cannot reassign 'self'"),
            "a_read_only_self": ("impl int {\n    fun inc(self) {\n        self = self + 1\n    }\n}\n\nfun main() {\n}\n",
                                 "cannot reassign 'self'"),
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
