"""Burn tests for the module system (v0.5.1): a committed multi-file example is
linked, type-checked, and run through both the interpreter and the native
compiler, which must agree (the core parity guarantee, extended to modules).

The interpreter is the self-hosted one (`myla run`); the native output is also
compared with the retired Python interpreter's recorded answer (MYLA-219)."""
import os
import tempfile
import unittest

from ._native import (
    CAN_BUILD_NATIVE,
    SKIP_REASON,
    build_and_run_checker,
    check_file,
    interpret_checker,
    run_file_both_now,
    selfhost_run,
    write_program,
)

MODULES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                 "examples", "modules")
)

EXPECTED = "7\ndone!\n7\n"


def _check_entry(entry: str):
    return check_file(os.path.join(MODULES_DIR, entry))


class TestModuleExample(unittest.TestCase):
    def test_interpreter(self):
        out, err, code = selfhost_run(os.path.join(MODULES_DIR, "main.my"))
        self.assertEqual((err, code), ("", 0))
        self.assertEqual(out, EXPECTED)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_native_matches_interpreter(self):
        program = _check_entry("main.my")
        native_out, code = build_and_run_checker(program)
        self.assertEqual(code, 0)
        self.assertEqual(native_out, EXPECTED)
        self.assertEqual(interpret_checker(program), native_out)


# Two modules, each deriving `Eq` for a type declared at the same line and
# column: each keeps its `Eq` (MYLA-364; the checker told derived types
# apart by their position, so one of them lost it).
SAME_PLACE_DUP = (
    "// the same line as main.my's derive\n"
    "#derive(Eq)\npub enum E { A, B }\n"
    "pub fun is_a(e: E) -> bool { return e == E.A }\n"
)
SAME_PLACE_MAIN = (
    "import .dup as dup\n"
    "#derive(Eq)\npub enum E { A, B }\n"
    "pub fun is_a(e: E) -> bool { return e == E.A }\n"
    "fun main() {\n    print(is_a(E.B))\n    print(dup.is_a(dup.E.A))\n}\n"
)


class TestDerivesAtTheSamePlace(unittest.TestCase):
    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_both_keep_their_eq(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_program(tmp, SAME_PLACE_DUP, "dup.my")
            path = write_program(tmp, SAME_PLACE_MAIN)
            self.assertEqual(run_file_both_now(path), ("false\ntrue\n", "", 0))


# A bound names a module's trait as a type names its type (MYLA-398, D170):
# `T: shapes.Area`, a generic one with its arguments, `P: shapes.Pair<T>`, a
# trait function's, `T: shapes.Zero`, and std.json's `T: json.ToJson`.
BOUND_SHAPES = (
    "pub trait Area {\n    fun area(self) -> int\n}\n"
    "pub trait Pair<T> {\n    fun first(self) -> T\n}\n"
    "pub trait Zero {\n    fun zero() -> Self\n}\n"
    "pub struct Sq {\n    side: int,\n}\n"
    "impl Area for Sq {\n    fun area(self) -> int { return self.side * self.side }\n}\n"
    "impl Zero for Sq {\n    fun zero() -> Sq { return Sq { side: 0 } }\n}\n"
)
BOUND_MAIN = (
    "import .shapes as shapes\n"
    "import std.json as json\n"
    "from .shapes import Sq\n"
    "struct Two {\n    a: str,\n    b: str,\n}\n"
    "impl shapes.Pair<str> for Two {\n    fun first(self) -> str { return self.a }\n}\n"
    "#derive(Eq, Json)\nstruct Pt {\n    x: int,\n}\n"
    "fun total<T: shapes.Area>(xs: [T]) -> int {\n    var n = 0\n    for x in xs { n += x.area() }\n    return n\n}\n"
    "fun head<P: shapes.Pair<T>, T>(p: P) -> T {\n    return p.first()\n}\n"
    "fun none<T: shapes.Zero + shapes.Area>() -> int {\n    return T.zero().area()\n}\n"
    "fun show<T: json.ToJson + Eq>(v: T, w: T) -> str {\n"
    "    if v == w { return json.encode(v) }\n    return \"-\"\n}\n"
    "fun main() {\n"
    "    print(total([Sq { side: 2 }, Sq { side: 3 }]))\n"
    "    print(head(Two { a: \"x\", b: \"y\" }))\n"
    "    print(none<Sq>())\n"
    "    print(show(Pt { x: 4 }, Pt { x: 4 }))\n"
    "}\n"
)


class TestBoundsNameAModulesTrait(unittest.TestCase):
    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_both_run_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_program(tmp, BOUND_SHAPES, "shapes.my")
            path = write_program(tmp, BOUND_MAIN)
            self.assertEqual(run_file_both_now(path), ('13\nx\n0\n{"x":4}\n', "", 0))


if __name__ == "__main__":
    unittest.main()
