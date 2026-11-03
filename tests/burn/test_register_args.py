"""Burn test: arguments in registers (MYLA-250, D119).

Myla's functions take their first six argument words in %rdi, %rsi, %rdx,
%rcx, %r8 and %r9, the rest on the stack, which the caller pops; a function
value's environment comes in %r10. Calls of every kind with 0 to 9 argument
words (direct calls, aggregate results, owned parameters, `become` with
words in registers and on the stack, a struct passed by value, function
values of lambdas and named functions, partial application, composition,
derived equality, async functions and an actor's method) print the same
natively and interpreted, with and without the task runtime."""
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_COMMON = """#derive(Eq)
struct P {
    x: int,
    y: int,
}

#derive(Eq)
struct Box3 {
    a: P,
    name: str,
    k: int64,
}

fun w0() -> int {
    return 7
}

fun w1(a: int) -> int {
    return a * 3 + 1
}

fun w6(a: int, b: int, c: int, d: int, e: int, f: int) -> int {
    return a + 2 * b + 3 * c + 4 * d + 5 * e + 6 * f
}

fun w7(a: int, b: int, c: int, d: int, e: int, f: int, g: int) -> int {
    return w6(a, b, c, d, e, f) + 7 * g
}

fun w9(a: int, b: str, c: int64, d: float, e: int, f: char, g: int, h: str, i: int) -> str {
    return f"{a} {b} {c} {d} {e} {f} {g} {h} {i}"
}

// an aggregate result (through the hidden pointer) with many arguments
fun make(a: int, b: int, c: int, d: int, e: int, f: int, g: int, h: str) -> Box3 {
    return Box3 { a: P { x: a + b + c, y: d + e + f }, name: h, k: (g as int64) * 1000000000i64 }
}

// a list kept: its parameter passed owned
fun keep(xs: [str], a: int, b: int, c: int, d: int, e: int, s: str, t: str) -> [str] {
    var out = xs
    out.push(s)
    out.push(t)
    out.push(f"{a + b + c + d + e}")
    return out
}

// `become` with arguments in registers, and with words on the stack
fun count_down(n: int, acc: int64) -> int64 {
    if n == 0 {
        return acc
    }
    become count_down(n - 1, acc + (n as int64))
}

fun spin(n: int, a: int, b: int, c: int, d: int, e: int, f: int, g: int) -> int {
    if n == 0 {
        return a + b + c + d + e + f + g
    }
    become spin(n - 1, b, c, d, e, f, g, a + 1)
}

// a struct handed over by `become`: passed by value (D88)
fun walk(p: P, n: int, a: int, b: int, c: int, d: int) -> int {
    if n == 0 {
        return p.x * 1000 + p.y + a + b + c + d
    }
    become walk(P { x: p.y, y: p.x + 1 }, n - 1, b, c, d, a)
}

// an implicit tail call needing more stack words than its caller received
fun small(n: int) -> int {
    return w7(n, n, n, n, n, n, n)
}

fun apply3(f: (int, int, int) -> int, a: int, b: int) -> int {
    return f(a, b, 10)
}

fun apply8(f: (int, int, int, int, int, int, int, int) -> int) -> int {
    return f(1, 2, 3, 4, 5, 6, 7, 8)
}

fun sum8(a: int, b: int, c: int, d: int, e: int, f: int, g: int, h: int) -> int {
    return a + 10 * b + 100 * c + 1000 * d - e - 2 * f - 3 * g - 4 * h
}

fun sum9(a: int, b: int, c: int, d: int, e: int, f: int, g: int, h: int, i: int) -> int {
    return sum8(a, b, c, d, e, f, g, h) * 10 + i
}

fun apply7(f: (int, int, int, int, int, int, int) -> int) -> int {
    return f(1, 2, 3, 4, 5, 6, 7)
}

// `become` through a function value, with a word on the stack
fun relay(f: (int, int, int, int, int, int, int) -> int, a: int, b: int, c: int, d: int, e: int, g: int) -> int {
    become f(a, b, c, d, e, g, 7)
}

fun make_p(a: int, b: int) -> P {
    return P { x: a, y: b }
}

fun via(f: (int, int) -> P, a: int) -> P {
    return f(a, a + 1)
}

fun inc(x: int) -> int {
    return x + 1
}

fun dbl(x: int) -> int {
    return x * 2
}

"""

_ASYNC = """async fun slow(a: int, b: int, c: int, d: int, e: int, f: int, g: int, s: str) -> str {
    await task.yield()
    return f"{s}{a + b + c + d + e + f + g}"
}

async fun gather(n: int) -> int {
    async let x = slow(n, 1, 2, 3, 4, 5, 6, "t")
    let y = await slow(1, 1, 1, 1, 1, 1, 1, "u")
    let s = await x
    return s.len() + y.len() + n
}

actor Tally {
    n: int64,
}

impl Tally {
    fun add(var self, a: int, b: int, c: int, d: int, e: int, f: int, g: int, h: str) -> str {
        self.n = self.n + ((a + b + c + d + e + f + g) as int64)
        return f"{h}{self.n}"
    }
}

import std.task as task
"""

_BODY = """    print(w0())
    print(w1(4))
    print(w6(1, 2, 3, 4, 5, 6))
    print(w7(1, 2, 3, 4, 5, 6, 7))
    print(w9(1, "two", 3i64, 4.5, 5, '6', 7, "eight", 9))
    let b = make(1, 2, 3, 4, 5, 6, 7, "box")
    print(f"{b.a.x} {b.a.y} {b.name} {b.k}")
    let b2 = make(1, 2, 3, 4, 5, 6, 7, "box")
    print(b == b2)
    print(b == make(1, 2, 3, 4, 5, 6, 8, "box"))
    var xs: [str] = ["a"]
    xs = keep(xs, 1, 2, 3, 4, 5, "s", "t")
    print(xs.len())
    print(xs[3])
    print(count_down(100000, 0i64))
    print(spin(100001, 1, 2, 3, 4, 5, 6, 7))
    print(walk(P { x: 1, y: 2 }, 11, 1, 2, 3, 4))
    print(small(3))
    let k = 5
    print(apply3((a: int, b: int, c: int) => a * 100 + b * 10 + c + k, 1, 2))
    print(apply8(sum8))
    print(apply8((a: int, b: int, c: int, d: int, e: int, f: int, g: int, h: int) => a + b + c + d + e + f + g + h + k))
    let part = sum8(_, 2, _, 4, 5, _, 7, 8)
    print(apply3(part, 1, 3))
    let p7 = sum9(_, _, _, _, _, _, _, 8, 9)
    print(apply7(p7))
    let s7 = sum8(_, _, _, _, _, _, _, 8)
    print(relay(s7, 2, 3, 4, 5, 1, 6))
    let wf = walk
    print(wf(P { x: 5, y: 6 }, 3, 1, 2, 3, 4))
    let p = via(make_p, 4)
    print(f"{p.x} {p.y}")
    let mk = make_p(_, 9)
    let q = mk(3)
    print(f"{q.x} {q.y}")
    let both = inc >> dbl
    print(both(20))
    let lam = (x: int) => x + k
    let chain = lam >> inc >> dbl
    print(chain(1))
"""

_ASYNC_BODY = """    print(await gather(3))
    print(await slow(1, 2, 3, 4, 5, 6, 7, "z"))
    let t = Tally { n: 0i64 }
    print(await t.add(1, 2, 3, 4, 5, 6, 7, "n"))
    print(await t.add(1, 1, 1, 1, 1, 1, 1, "m"))
"""

SYNC = _COMMON + "fun main() {\n" + _BODY + "}\n"
ASYNC = _COMMON + _ASYNC + "#main\nasync fun main() {\n" + _BODY + _ASYNC_BODY + "}\n"

EXPECTED = """7
13
91
140
1 two 3 4.5 5 6 7 eight 9
6 15 box 7000000000
true
false
4
15
5000050000
100029
7017
84
135
4251
41
4243
42519
5366
7017
4 5
3 9
42
14
"""

EXPECTED_ASYNC = EXPECTED + """8
z28
n28
m35
"""


def _function(asm: str, name: str) -> str:
    m = re.search(rf"^myla_{name}:\n(.*?)(?=^myla_[\w.]+:|\Z)", asm, re.S | re.M)
    if not m:
        raise AssertionError(f"no function {name}")
    return m.group(1)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class RegisterArguments(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name: str, text: str) -> str:
        path = os.path.join(self.tmp.name, name + ".my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def same(self, name: str, text: str, expected: str) -> None:
        path = self.write(name, text)
        myla = selfhost_tool("main")
        ran = subprocess.run([myla, "run", path], capture_output=True, text=True)
        self.assertEqual((ran.stdout, ran.returncode), (expected, 0), ran.stderr)
        exe = os.path.join(self.tmp.name, name)
        built = subprocess.run([myla, "build", path, "-o", exe], capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        native = subprocess.run([exe], capture_output=True, text=True)
        self.assertEqual((native.stdout, native.returncode), (expected, 0), native.stderr)

    def test_calls_print_the_same(self):
        self.same("calls", SYNC, EXPECTED)

    def test_calls_with_tasks_print_the_same(self):
        self.same("tasks", ASYNC, EXPECTED_ASYNC)

    def asm(self, text: str) -> str:
        path = self.write("code", text)
        return subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT], capture_output=True, text=True,
                              check=True).stdout

    def test_arguments_travel_in_registers(self):
        asm = self.asm(SYNC)
        # six words and fewer: nothing pushed, nothing read above the frame
        for name in ("w1", "w6", "count_down"):
            body = _function(asm, name)
            self.assertNotRegex(body, r"(?<![-\w])(1[6-9]|[2-9][0-9])\(%rbp\)", name)
            self.assertNotIn("ret $", body, name)
        self.assertNotRegex(_function(asm, "w7").split("call myla_w6")[0], r"pushq (?!%rbp)")
        # the seventh word on the stack, popped by the caller
        main = _function(asm, "main")
        self.assertRegex(main, r"call myla_w7\n\taddq \$8, %rsp")

    def test_become_reuses_the_frame(self):
        body = _function(self.asm(SYNC), "spin")
        self.assertIn("jmp myla_spin", body)
        self.assertNotIn("call myla_spin", body)


if __name__ == "__main__":
    unittest.main()
