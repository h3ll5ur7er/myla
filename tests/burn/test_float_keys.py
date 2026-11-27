"""Burn test: floats are `Hash` (D198, MYLA-586).

A float, and a tuple, list, `Option` or `#derive(Eq, Hash)` struct holding
one, is a map key; `-0.0` and `0.0`, which are `==`, are one key; hashing a
NaN is the runtime error `cannot hash NaN`, in the interpreter and natively
alike, so its message and place agree: a map operation's at its key, or at
the call of a std.map or std.set method that reports its caller's position,
a float, a tuple's or a derived struct's member (MYLA-850); a NaN inside a
list or an enum, and `x.hash(h)` called by a program, at std.hash's `hash`."""
import tempfile
import unittest

from tests.burn._native import (CAN_BUILD_NATIVE, SKIP_REASON, Program, build_and_run_full, run_source_both_now,
                                selfhost_run, shown, write_program)

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

NAN_KEY = """import std.set as set
import std.map as map

#derive(Eq, Hash)
struct Point {
    x: float,
    y: float,
}

fun main() {
    var m: [float: int] = [:]
    m[1.0] = 1
    let z = 0.0
    var cells: [(int, float): int] = [:]
    var seen: [Point: bool] = [:]
    var s: set.Set<float> = set.new()
    var lists: [[float]: int] = [:]
    var opts: [Option<float32>: int] = [:]
    // the case
    print(m.len())
}
"""

# (case, its line, the text at whose start the error is, a call's at its
# parenthesis: None for std.hash)
NAN_CASES = [
    ("an insert", "    m[z / z] = 2", "z / z"),
    ("a lookup", "    print(m[z / z])", "z / z"),
    ("a compound assignment", "    m[z / z] += 1", "z / z"),
    ("contains", "    print(m.contains(z / z))", "z / z"),
    ("remove", "    m.remove(z / z)", "z / z"),
    ("a literal", "    let lit = [z / z: 1]", "z / z"),
    ("get", "    print(m.get(z / z) == None)", "(z / z) =="),
    ("get_or", "    print(m.get_or(z / z, 0))", "(z / z, 0)"),
    ("update", "    m.update(z / z, 0, (n) => n + 1)", "(z / z, 0,"),
    ("counts", "    let c = map.counts([1.0, z / z])", "([1.0"),
    ("a set's insert", "    let added = s.insert(z / z)", "(z / z)"),
    ("a set's contains", "    print(s.contains(z / z))", "(z / z))"),
    ("set.of", "    let t = set.of([z / z])", "([z / z])"),
    ("in a tuple", "    cells[(1, z / z)] = 1", "(1, z / z)"),
    ("in a derived struct", "    seen[Point { x: 0.5, y: z / z }] = true", "Point"),
    ("in a list", "    lists[[z / z]] = 1", None),
    ("in an Option", "    opts[Some((z / z) as float32)] = 1", None),
    ("hashed by the program", "    let h = (z / z).hash(Hasher { state: 0 })", None),
]


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class FloatKeys(unittest.TestCase):
    def test_in_the_interpreter_and_natively(self) -> None:
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_a_nan_key_is_a_runtime_error_at_the_program_s_line(self) -> None:
        # the same message and place; native code prints those two lines,
        # the interpreter the source line under them too
        for name, line, at in NAN_CASES:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                source = NAN_KEY.replace("    // the case\n", line + "\n")
                path = write_program(tmp, source)
                interp = selfhost_run(path)
                native = build_and_run_full(Program(path), argv0=path)
                for out, err, code in (interp, native):
                    self.assertEqual((out, code), ("", 1), err)
                    self.assertTrue(err.startswith("runtime error: cannot hash NaN\n  --> "), err)
                where = interp[1].split("\n")[1]
                if at is None:
                    self.assertIn("std/hash.my:", where)
                else:
                    # the line, and the column of the key or the call (a
                    # binary operation's is its operator's, two on)
                    row = source.split("\n").index(line) + 1
                    self.assertIn(where, [f"  --> {shown(path)}:{row}:{line.index(at) + 1}",
                                          f"  --> {shown(path)}:{row}:{line.index(at) + 3}"])
                self.assertEqual(interp[1].split("\n")[:2], native[1].split("\n")[:2])

if __name__ == "__main__":
    unittest.main()
