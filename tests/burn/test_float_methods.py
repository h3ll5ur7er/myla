"""Burn test: floats have methods (D199, MYLA-585).

`std.float` is implicit, as `std.int` is (D164): `x.sqrt()`, `x.floor()`,
`a.atan2(b)`, `x.is_nan()`, `x.to_bits()` work on a float64 and a float32
in every program without an import, and alike in the interpreter and
natively; its constants and free functions need `import std.float as
float`. A program's own method of one of its names on a float is a duplicate
naming the module."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_source_both_now
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

PROGRAM = """import std.float as float

fun main() {
    let x = -2.75
    print(x.abs())
    print(x.floor())
    print(x.ceil())
    print(x.round())
    print(x.trunc())
    print(x.fract())
    print(x.signum())
    print(16.0.sqrt() + 27.0.cbrt())
    print(3.0.hypot(4.0))
    print(2.0.powi(10))
    print(1.0.atan2(1.0) * 4.0 == float.PI)
    print(float.PI.to_degrees())
    print(2.0.lerp(4.0, 0.25))
    print(5.0.clamp(0.0, 1.0))
    print(1000.0.log10())
    print(float.nan().is_nan())
    print((1.0 / 0.0).is_infinite())
    print(f"{1.0.to_bits():#x}")
    print(float.from_bits(0x4004000000000000u64))
    print((-0.0).total_cmp(0.0))
    var xs = [3.5, -1.0, 2.0, -0.0, 0.0]
    xs.sort_by((a: float, b: float) => a.total_cmp(b) < 0)
    print(f"{xs[0]} {xs[1]} {xs[4]}")
    let y: float32 = 2.0
    print(y.sqrt())
    print(y.powi(3))
    print(f"{y.to_bits():#x}")
    print(float.from_bits32(0xC0200000u32))
    print((0.1 + 0.2).approx_eq(0.3, 1e-12))
}
"""

WANT = """2.75
-3
-2
-3
-2
-0.75
-1
7
5
1024
true
180
2.5
1
3
true
true
0x3ff0000000000000
2.5
-1
-1 -0 3.5
1.4142135
8
0x40000000
-2.5
true
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class FloatMethods(unittest.TestCase):
    def setUp(self) -> None:
        self.myla = selfhost_tool("main")

    def check(self, src: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "e.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)
            return subprocess.run([self.myla, "check", path, "--stdlib", STDLIB_ROOT],
                                  capture_output=True, text=True)

    def test_in_the_interpreter_and_natively(self) -> None:
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_a_programs_own_method_of_the_name_is_a_duplicate(self) -> None:
        proc = self.check("impl float64 {\n    fun sqrt(self) -> float64 {\n        return self\n    }\n}\n\nfun main() {}\n")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("duplicate method 'sqrt' for type 'float64'", proc.stderr)
        self.assertIn("std.float, which every program sees", proc.stderr)

    def test_a_new_name_is_fine(self) -> None:
        proc = self.check("impl float64 {\n    fun half(self) -> float64 {\n        return self / 2.0\n    }\n}\n\nfun main() {\n    print(3.0.half().sqrt())\n}\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_the_free_functions_need_the_import(self) -> None:
        proc = self.check("fun main() {\n    print(float.PI)\n}\n")
        self.assertEqual(proc.returncode, 1, proc.stderr)

    def test_loaded_only_where_a_float_method_may_be_called(self) -> None:
        # D258: a library whose std/float.my doesn't parse shows whether a
        # program loads it. One that calls no method of its names, and has
        # no impl on a float type, doesn't, nor the std.math it imports.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "lib", "std"))
            with open(os.path.join(tmp, "lib", "std", "float.my"), "w", encoding="utf-8") as fh:
                fh.write("this is not myla\n")
            cases = [
                ("fun main() {\n    print(1.5)\n    let xs = [1]\n    print(xs.len())\n}\n", False),
                ("fun main() {\n    print(2.0.sqrt())\n}\n", True),
                ("fun main() {\n    let x = 2.0\n    print(f\"{x . abs ()}\")\n}\n", True),
                ("fun main() {\n    print(3.max(4))\n}\n", True),     # a name of both, read as a float's
                ("impl float32 {\n    fun twice(self) -> float32 {\n        return self * 2.0\n    }\n}\n\nfun main() {}\n", True),
            ]
            for i, (src, loads) in enumerate(cases):
                with self.subTest(src=src):
                    path = os.path.join(tmp, f"p{i}.my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(src)
                    proc = subprocess.run([self.myla, "check", path, "--stdlib", os.path.join(tmp, "lib")],
                                          capture_output=True, text=True)
                    if loads:
                        self.assertIn("float.my", proc.stderr)
                    else:
                        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "ok"), proc.stderr)

    def test_the_loaders_names_are_std_floats_methods(self) -> None:
        # the loader's list of the names that load std.float (D258) is the
        # module's methods, at both widths
        import re
        with open(os.path.join(STDLIB_ROOT, "std", "float.my"), encoding="utf-8") as fh:
            text = fh.read()
        widths = re.split(r"^impl float32 \{$", text, flags=re.M)
        self.assertEqual(len(widths), 2)
        f64 = set(re.findall(r"^    fun (\w+)\(", widths[0], flags=re.M))
        f32 = set(re.findall(r"^    fun (\w+)\(", widths[1], flags=re.M))
        self.assertEqual(f64, f32)
        with open(os.path.join(os.path.dirname(STDLIB_ROOT), "selfhost", "loader.my"), encoding="utf-8") as fh:
            loader = fh.read()
        m = re.search(r"pub fun float_method_names\(\) -> \[str\] \{\n    return \[([^\]]*)\]", loader)
        self.assertIsNotNone(m, "selfhost/loader.my has float_method_names")
        self.assertEqual(set(re.findall(r'"(\w+)"', m.group(1))), f64)


if __name__ == "__main__":
    unittest.main()
