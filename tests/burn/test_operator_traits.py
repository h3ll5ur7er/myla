"""Burn test: operators between different types (D198, MYLA-584).

The operator traits take type arguments: `Add<R, O>`, `Sub`, `Mul`, `Div`,
`Rem` with `fun add(self, other: R) -> O`, where a bare `Mul` is
`Mul<Self, Self>` and `Mul<R>` is `Mul<R, Self>`; `Neg<O>` (`fun neg(self) ->
O`, bare `Neg<Self>`) gives unary `-`; `Index<I, O>` (`fun index(self, i: I)
-> O`) gives `v[i]` and `IndexSet<I, V>` (`fun set_index(var self, i: I, v:
V)`) gives `v[i] = x`. A type may implement one trait for several right-hand
types; an impl on a built-in number takes a struct or enum on the right (the
scalar on the left, `2.0 * v`). Generic code names what it needs, `T: Add +
Mul<float>`, and runs for a struct and for a number alike. The interpreter
and native code agree."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_source_both_now
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

PROGRAM = """#derive(Eq)
struct Vec2 {
    x: float,
    y: float,
}

impl Format for Vec2 {
    fun format(self, spec: str) -> str {
        return f"({self.x}, {self.y})"
    }
}

impl Add for Vec2 {
    fun add(self, other: Vec2) -> Vec2 {
        return Vec2 { x: self.x + other.x, y: self.y + other.y }
    }
}

impl Sub for Vec2 {
    fun sub(self, other: Vec2) -> Vec2 {
        return Vec2 { x: self.x - other.x, y: self.y - other.y }
    }
}

// `Mul<float>` is `Mul<float, Vec2>`: the scalar on the right
impl Mul<float> for Vec2 {
    fun mul(self, k: float) -> Vec2 {
        return Vec2 { x: self.x * k, y: self.y * k }
    }
}

// the same type on both sides, another result: the dot product
impl Mul<Vec2, float> for Vec2 {
    fun mul(self, other: Vec2) -> float {
        return self.x * other.x + self.y * other.y
    }
}

// the scalar on the left
impl Mul<Vec2, Vec2> for float64 {
    fun mul(self, v: Vec2) -> Vec2 {
        return Vec2 { x: self * v.x, y: self * v.y }
    }
}

impl Div<float> for Vec2 {
    fun div(self, k: float) -> Vec2 {
        return Vec2 { x: self.x / k, y: self.y / k }
    }
}

impl Neg for Vec2 {
    fun neg(self) -> Vec2 {
        return Vec2 { x: -self.x, y: -self.y }
    }
}

impl Index<int, float> for Vec2 {
    fun index(self, i: int) -> float {
        if i == 0 { return self.x }
        if i == 1 { return self.y }
        panic(f"index {i} out of range for a Vec2")
    }
}

impl IndexSet<int, float> for Vec2 {
    fun set_index(var self, i: int, v: float) {
        if i == 0 { self.x = v } else if i == 1 { self.y = v } else { panic(f"index {i} out of range for a Vec2") }
    }
}

struct Mat2 {
    a: float,
    b: float,
    c: float,
    d: float,
}

impl Mul<Vec2, Vec2> for Mat2 {
    fun mul(self, v: Vec2) -> Vec2 {
        return Vec2 { x: self.a * v.x + self.b * v.y, y: self.c * v.x + self.d * v.y }
    }
}

impl Mul for Mat2 {
    fun mul(self, o: Mat2) -> Mat2 {
        return Mat2 { a: self.a * o.a + self.b * o.c, b: self.a * o.b + self.b * o.d, c: self.c * o.a + self.d * o.c, d: self.c * o.b + self.d * o.d }
    }
}

// beside the classic `Mul`: a float literal on the right picks this one
impl Mul<float> for Mat2 {
    fun mul(self, k: float) -> Mat2 {
        return Mat2 { a: self.a * k, b: self.b * k, c: self.c * k, d: self.d * k }
    }
}

impl Index<(int, int), float> for Mat2 {
    fun index(self, rc: (int, int)) -> float {
        let (r, c) = rc
        if r == 0 { return if c == 0 { self.a } else { self.b } }
        return if c == 0 { self.c } else { self.d }
    }
}

#derive(Eq)
// float32 beside a classic `Mul`: the float literal takes the float32 impl
struct Narrow {
    v: float32,
}

impl Mul for Narrow {
    fun mul(self, o: Narrow) -> Narrow {
        return Narrow { v: self.v * o.v }
    }
}

impl Mul<float32> for Narrow {
    fun mul(self, k: float32) -> Narrow {
        return Narrow { v: self.v * k }
    }
}

#derive(Eq)
enum Sign {
    Plus,
    Minus,
}

impl Neg<Sign> for Sign {
    fun neg(self) -> Sign {
        return match self {
            Plus => Sign.Minus
            Minus => Sign.Plus
        }
    }
}

struct Box<T> {
    v: T,
}

// a generic impl with a right operand of its own
impl<T> Mul<int, [T]> for Box<T> {
    fun mul(self, n: int) -> [T] {
        var out: [T] = []
        var i = 0
        while i < n {
            out.push(self.v)
            i += 1
        }
        return out
    }
}

struct Body {
    pos: Vec2,
    vel: Vec2,
}

impl Body {
    fun step(var self, dt: float) {
        self.pos += self.vel * dt
        self.vel[1] -= 1.0
    }
}

fun lerp<T: Add + Sub + Mul<float>>(a: T, b: T, t: float) -> T {
    return a + (b - a) * t
}

fun negate<T: Neg>(x: T) -> T {
    return -x
}

fun first<C: Index<int, float>>(c: C) -> float {
    return c[0]
}

fun main() {
    let u = Vec2 { x: 1.0, y: 2.0 }
    let v = Vec2 { x: 3.0, y: -1.0 }
    print(u + v)
    print(u * 2.0)
    print(2.0 * u)
    print(u * v)
    print(v / 2.0)
    print(-u)
    print(-u * 3.0 + v)
    print(u[0] + u[1])
    let m = Mat2 { a: 0.0, b: -1.0, c: 1.0, d: 0.0 }
    print(m * u)
    print(m * m * u)
    print(m[(0, 1)])
    print((m * 2.0)[(0, 1)] + (m * m * -1.0)[(0, 0)])
    print((Narrow { v: 1.5 } * 2.0 * Narrow { v: 2.0 }).v)
    var p = Vec2 { x: 0.0, y: 0.0 }
    let vel = Vec2 { x: 1.0, y: 0.5 }
    p += vel * 2.0
    p *= 3.0
    p[1] = 5.0
    p[0] += 1.5
    print(p)
    print(p == Vec2 { x: 7.5, y: 5.0 })
    print(lerp(u, v, 0.5))
    print(lerp(1.0, 3.0, 0.25))
    print(negate(u))
    print(negate(5))
    print(first(v))
    let s = -Sign.Plus
    print(s == Sign.Minus)
    let b = Box { v: "ab" }
    let bs = b * 3
    print(bs.len())
    var body = Body { pos: u, vel: v }
    body.step(0.5)
    body.step(0.5)
    print(body.pos)
    var vs = [u, v]
    vs[1][0] = 9.0
    vs[0] *= -1.0
    print(vs[0] + vs[1])
    let f = (k: float) => u * k + v
    print(f(2.0))
}
"""

WANT = """(4, 1)
(2, 4)
(2, 4)
1
(1.5, -0.5)
(-1, -2)
(0, -7)
3
(-2, 1)
(-1, -2)
-1
-1
6
(7.5, 5)
true
(2, 0.5)
1.5
(-1, -2)
-5
3
true
3
(4, 0.5)
(8, -3)
(5, 3)
"""

# operators in async functions, their frames (D92) holding the operands
ASYNC_PROGRAM = """import std.task as task

struct V {
    x: float,
    y: float,
}

impl Mul<float> for V {
    fun mul(self, k: float) -> V {
        return V { x: self.x * k, y: self.y * k }
    }
}

impl Neg for V {
    fun neg(self) -> V {
        return V { x: -self.x, y: -self.y }
    }
}

async fun scaled(v: V, k: float) -> V {
    await task.yield()
    let w = -v * k
    await task.yield()
    return w * 2.0
}

#main
async fun main() {
    async let a = scaled(V { x: 1.0, y: 2.0 }, 3.0)
    let b = await scaled(V { x: 0.5, y: 0.0 }, 1.0)
    let r = await a
    print(r.x + b.x)
    print(r.y)
}
"""

ASYNC_WANT = "-7\n-12\n"

_VEC = """struct V {
    x: float,
}

"""

# (program, the message it must give)
ERRORS = [
    # an integer literal never becomes a float, beside an operator either
    (_VEC + "impl Mul<float> for V {\n    fun mul(self, k: float) -> V { return V { x: self.x * k } }\n}\n\nfun main() {\n    let v = V { x: 1.0 }\n    let w = v * 2\n}\n",
     "operator '*' is not defined for 'V' and 'int32'"),
    (_VEC + "fun main() {\n    let v = V { x: 1.0 }\n    let w = v * 2.0\n}\n",
     "operator '*' is not defined for 'V': it needs 'impl Mul for V'"),
    (_VEC + "fun main() {\n    let v = V { x: 1.0 }\n    let w = -v\n}\n",
     "unary '-' is not defined for 'V': it needs 'impl Neg for V'"),
    (_VEC + "fun main() {\n    let v = V { x: 1.0 }\n    let w = v[0]\n}\n",
     "type 'V' can't be indexed: it needs 'impl Index<int32, …> for V'"),
    (_VEC + "impl Index<int, float> for V {\n    fun index(self, i: int) -> float { return self.x }\n}\n\nfun main() {\n    var v = V { x: 1.0 }\n    v[0] = 2.0\n}\n",
     "cannot assign to an index of 'V': it needs 'impl IndexSet<int32, float64> for V'"),
    (_VEC + "impl IndexSet<int, float> for V {\n    fun set_index(var self, i: int, x: float) { self.x = x }\n}\n\nfun main() {\n    let v = V { x: 1.0 }\n    v[0] = 2.0\n}\n",
     "cannot assign to an immutable binding"),
    (_VEC + "impl Mul<float> for V {\n    fun mul(self, k: float) -> V { return self }\n}\n\nimpl Mul<float, float> for V {\n    fun mul(self, k: float) -> float { return k }\n}\n",
     "duplicate impl of trait 'Mul<float64, …>' for type 'V'"),
    ("struct B<T> {\n    v: T,\n}\n\nimpl<T> Mul<T, B<T>> for B<T> {\n    fun mul(self, k: T) -> B<T> { return self }\n}\n",
     "the right operand of an operator impl can't use the impl's type parameters"),
    ("impl Mul<int, float> for float64 {\n    fun mul(self, k: int) -> float { return self }\n}\n",
     "an operator impl on 'float64' needs a struct or enum on the right"),
    (_VEC + "fun scale<T: Mul<float>>(a: T) -> T {\n    return a * 2\n}\n",
     "operator '*' on a value of type parameter 'T' is not defined for 'int32'"),
    (_VEC + "impl Mul<float> for V {\n    fun mul(self, k: float) -> V { return self }\n}\n\nfun scale<T: Mul<float>>(a: T) -> T {\n    return a * 2.0\n}\n\nfun main() {\n    let s = scale(\"x\")\n}\n",
     "type 'str' does not satisfy the bound 'T: Mul<float64>' required by 'scale'"),
]


# `#test` cases above operator methods: the native harness calls them through
# their operators, as a method beside others of its trait is renamed for its
# right operand's type
CASES = """#derive(Eq)
struct V {
    x: float,
}

impl Mul<float> for V {
    #test(V { x: 2.0 }, 3.0)[V { x: 6.0 }]
    fun mul(self, k: float) -> V {
        return V { x: self.x * k }
    }
}

impl Mul for V {
    #test(V { x: 2.0 }, V { x: 4.0 })[V { x: 8.0 }]
    fun mul(self, o: V) -> V {
        return V { x: self.x * o.x }
    }
}

impl Neg for V {
    #test(V { x: 2.0 })[V { x: -2.0 }]
    fun neg(self) -> V {
        return V { x: -self.x }
    }
}

impl Index<int, float> for V {
    #test(V { x: 2.0 }, 0)[2.0]
    fun index(self, i: int) -> float {
        return self.x
    }
}

impl IndexSet<int, float> for V {
    #test(V { x: 2.0 }, 0, 5.0)[()]
    fun set_index(var self, i: int, v: float) {
        self.x = v
    }
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class OperatorTraits(unittest.TestCase):
    def setUp(self) -> None:
        self.myla = selfhost_tool("main")

    def test_in_the_interpreter_and_natively(self) -> None:
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_in_async_functions(self) -> None:
        self.assertEqual(run_source_both_now(ASYNC_PROGRAM), (ASYNC_WANT, "", 0))

    def test_cases_on_operator_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cases.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(CASES)
            for flags in ([], ["--native"]):
                with self.subTest(flags=flags):
                    proc = subprocess.run([self.myla, "test", path, "--stdlib", STDLIB_ROOT, *flags],
                                          capture_output=True, text=True, cwd=tmp)
                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                    self.assertIn("5/5 passed.", proc.stdout)

    def test_errors(self) -> None:
        for src, want in ERRORS:
            with self.subTest(want=want), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "e.my")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(src)
                proc = subprocess.run([self.myla, "check", path, "--stdlib", STDLIB_ROOT],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn(want, proc.stderr)


if __name__ == "__main__":
    unittest.main()
