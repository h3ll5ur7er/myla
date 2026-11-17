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


class TestModuleIdCollision(unittest.TestCase):
    def test_it_is_reported_at_the_import(self):
        # `proj/up/a.my` and `a.my` above the project root are both `up$a`:
        # the error is at the import that loads the second (MYLA-418; it
        # had no position)
        import subprocess
        from ._tools import STDLIB_ROOT, selfhost_tool
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "proj", "up"))
            write_program(tmp, "pub fun g() -> int {\n    return 1\n}\n", "a.my")
            write_program(os.path.join(tmp, "proj", "up"), "pub fun f() -> int {\n    return 2\n}\n", "a.my")
            write_program(os.path.join(tmp, "proj"),
                          "from .up.a import f\nfrom ..a import g\n\nfun main() {\n    print(f() + g())\n}\n")
            proc = subprocess.run([selfhost_tool("main"), "check", os.path.join("proj", "main.my"),
                                   "--stdlib", STDLIB_ROOT], capture_output=True, text=True, cwd=tmp)
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(proc.stderr.startswith(
                "module error: module id collision 'up$a' between proj/up/a.my and a.my\n"
                "  --> proj/main.my:2:6\n"), proc.stderr)


# D257 (MYLA-790): any module may implement any trait for any type, an
# operator's included: `extra` gives `geo.V` a `Neg`, and the entry a
# `Mul<str, str>` beside geo's own `Mul<int>`
IMPLS_GEO = 'pub struct V {\n    x: int,\n}\n\nimpl Mul<int> for V {\n    fun mul(self, k: int) -> V {\n        return V { x: self.x * k }\n    }\n}\n'
IMPLS_EXTRA = 'from .geo import V\n\n// any module may implement any trait for any type (D257)\nimpl Neg<int> for V {\n    fun neg(self) -> int {\n        return -self.x\n    }\n}\n\npub fun twice(n: int) -> int {\n    return -(V { x: n * 2 })\n}\n'
IMPLS_MAIN = 'from .geo import V\nfrom .extra import twice\n\n// any module may implement any trait for any type (D257): the type\'s own\n// `Mul<int>` beside this one\nimpl Mul<str, str> for V {\n    fun mul(self, k: str) -> str {\n        return f"{self.x}{k}"\n    }\n}\n\nfun main() {\n    print((V { x: 2 } * 3).x)\n    print(V { x: 2 } * "a")\n    print(twice(1))\n}\n'


class TestImplsAcrossModules(unittest.TestCase):
    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_any_module_may_implement_a_trait(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_program(tmp, IMPLS_GEO, "geo.my")
            write_program(tmp, IMPLS_EXTRA, "extra.my")
            path = write_program(tmp, IMPLS_MAIN)
            self.assertEqual(run_file_both_now(path), ("6\n2a\n-2\n", "", 0))

    def test_two_impls_with_the_same_arguments_are_both_named(self):
        # wherever they are: the error at one, a note naming the other, by
        # its file when it is another's, by its module when it is the
        # library's; the error is at the program's impl, not the library's
        import subprocess
        from ._tools import STDLIB_ROOT, selfhost_tool
        again = IMPLS_MAIN.replace("impl Mul<str, str> for V {\n    fun mul(self, k: str) -> str {\n        return f\"{self.x}{k}\"",
                                   "impl Mul<int> for V {\n    fun mul(self, k: int) -> V {\n        return self")
        self.assertNotEqual(again, IMPLS_MAIN)
        vec = ("from std.vector32 import Vec3\n\nimpl Mul<float32> for Vec3 {\n    fun mul(self, k: float32) -> Vec3 {\n"
               "        return self\n    }\n}\n\nfun main() {\n}\n")
        for main, want in (
            (again, "type error: duplicate impl of trait 'Mul<int32, …>' for type 'geo.V' (one per type of the right "
                    "operand or index)\n  --> geo.my:5:1\n"),
            (vec, "type error: duplicate impl of trait 'Mul<float32, …>' for type 'vector32.Vec3' (one per type of the "
                  "right operand or index)\n  --> main.my:3:1\n"),
        ):
            with self.subTest(want=want), tempfile.TemporaryDirectory() as tmp:
                write_program(tmp, IMPLS_GEO, "geo.my")
                write_program(tmp, IMPLS_EXTRA, "extra.my")
                write_program(tmp, main)
                proc = subprocess.run([selfhost_tool("main"), "check", "main.my", "--stdlib", STDLIB_ROOT],
                                      capture_output=True, text=True, cwd=tmp)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertTrue(proc.stderr.startswith(want), proc.stderr)
                if main is again:
                    self.assertIn("\nnote: the other impl is at main.my:6:1\n", proc.stderr + "\n")
                else:
                    self.assertRegex(proc.stderr, r"\nnote: the other impl is std\.vector32's, at \S*std/vector32\.my:\d+:1\n")


class TestARootStdFolderIsRefused(unittest.TestCase):
    def test_it_is_reported_at_the_import(self):
        # D255 (MYLA-790, MYLA-584): a program's own `std/` folder (or
        # `std.my`) at its root would be named as the library's modules
        # are, `std$process`, and got their privileges: an empty `exit` of
        # its `std/process.my` passed for one that never returns, and its
        # `std/fmt.my` collided with std.fmt in a build. The loader refuses
        # it at the import, for every command; a `std/` below the root is
        # any folder
        import subprocess
        from ._tools import STDLIB_ROOT, selfhost_tool
        cases = (
            ("std/process.my", "pub fun exit(code: int) { }\n",
             "from .std.process import exit\nfun f(n: int) -> str {\n    if n > 0 { return \"pos\" }\n    exit(1)\n}\n"
             "fun main() {\n    print(f(0))\n}\n", ".std.process"),
            ("std/task.my", "pub fun cancel(x: int) -> int {\n    return x + 1\n}\n",
             "from .std.task import cancel\nfun main() {\n    print(cancel(1))\n}\n", ".std.task"),
            ("std/fmt.my", "pub fun fmt_int(a: int) -> int {\n    return a + 1\n}\n",
             "from .std.fmt import fmt_int\nfun main() {\n    let a = 5\n    print(f\"{a:>4}|{fmt_int(a)}\")\n}\n", ".std.fmt"),
            ("std.my", "pub fun one() -> int {\n    return 1\n}\n",
             "from .std import one\nfun main() {\n    print(one())\n}\n", ".std"),
        )
        for module, text, main, dotted in cases:
            for cmd in ("check", "run", "build"):
                with self.subTest(module=module, cmd=cmd), tempfile.TemporaryDirectory() as tmp:
                    os.makedirs(os.path.join(tmp, "std"))
                    write_program(tmp, text, module)
                    write_program(tmp, main)
                    argv = [selfhost_tool("main"), cmd, "main.my", "--stdlib", STDLIB_ROOT]
                    if cmd == "build":
                        argv += ["-o", "prog"]
                    proc = subprocess.run(argv, capture_output=True, text=True, cwd=tmp)
                    self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                    self.assertTrue(proc.stderr.startswith(
                        f"module error: cannot import '{dotted}': a folder or file named 'std' at the program's "
                        "root is refused, as 'std' is the standard library (rename it)\n"
                        "  --> main.my:1:6\n"), proc.stderr)
        # below the root, `std` is a folder like any other
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "sub", "std"))
            write_program(os.path.join(tmp, "sub", "std"), "pub fun exit(code: int) { }\n", "process.my")
            write_program(tmp, "from .sub.std.process import exit\nfun main() {\n    exit(1)\n    print(2)\n}\n")
            proc = subprocess.run([selfhost_tool("main"), "run", "main.my", "--stdlib", STDLIB_ROOT],
                                  capture_output=True, text=True, cwd=tmp)
            self.assertEqual((proc.returncode, proc.stdout), (0, "2\n"), proc.stderr)


if __name__ == "__main__":
    unittest.main()
