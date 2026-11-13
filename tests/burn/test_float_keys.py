"""Burn test: floats are `Hash` (D196, MYLA-586).

A float, and a tuple, list, `Option` or `#derive(Eq, Hash)` struct holding
one, is a map key; `-0.0` and `0.0`, which are `==`, are one key; hashing a
NaN is the runtime error `cannot hash NaN`, raised by std.hash's own `hash`
in the interpreter and natively alike, so its message and place agree."""
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, Program, build_and_run_full, run_source_both_now, selfhost_run, write_program

PROGRAM = """#derive(Eq, Hash)
struct Point {
    x: float,
    y: float,
}

fun main() {
    var m: [float: str] = [:]
    m[1.5] = "one and a half"
    m[0.0] = "zero"
    m[-0.0] = "minus zero"
    m[1e300] = "big"
    print(m.len())
    print(m.get_or(0.0, "?"))
    print(m.get_or(1.5, "?"))
    var cells: [(float, float): int] = [:]
    cells[(0.5, 0.25)] = 1
    cells[(0.5, 0.25)] += 1
    print(cells[(0.5, 0.25)])
    var seen: [Point: bool] = [:]
    seen[Point { x: 1.0, y: -2.0 }] = true
    print(seen.contains(Point { x: 1.0, y: -2.0 }))
    print(seen.contains(Point { x: 1.0, y: 2.0 }))
    var narrow: [float32: int] = [:]
    narrow[0.1f32] = 1
    narrow[-0.0f32] = 2
    narrow[0.0f32] = 3
    print(narrow.len())
    print(narrow[0.1f32] + narrow[0.0f32])
    var opt: [Option<float>: int] = [:]
    opt[Some(2.5)] = 7
    opt[None] = 8
    print(opt[Some(2.5)] + opt[None])
    var lists: [[float]: int] = [:]
    lists[[1.0, 2.0]] = 3
    print(lists[[1.0, 2.0]])
}
"""

WANT = """3
minus zero
one and a half
2
true
false
2
4
15
3
"""

NAN_KEY = """fun main() {
    var m: [float: int] = [:]
    m[1.0] = 1
    let z = 0.0
    m[z / z] = 2
    print(m.len())
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class FloatKeys(unittest.TestCase):
    def test_in_the_interpreter_and_natively(self) -> None:
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_a_nan_key_is_a_runtime_error(self) -> None:
        # the same message and place; native code prints those two lines,
        # the interpreter the source line under them too
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, NAN_KEY)
            interp = selfhost_run(path)
            native = build_and_run_full(Program(path), argv0=path)
        for out, err, code in (interp, native):
            self.assertEqual((out, code), ("", 1))
            self.assertTrue(err.startswith("runtime error: cannot hash NaN\n  --> "), err)
            self.assertIn("std/hash.my:", err.split("\n")[1])
        self.assertEqual(interp[1].split("\n")[:2], native[1].split("\n")[:2])


if __name__ == "__main__":
    unittest.main()
