"""Burn tests: integer overflow (D175, MYLA-395). `+`, `-`, `*`, unary `-` and
the signed minimum divided by -1 trap with `integer overflow`, and a shift whose
count isn't below the width with `shift amount out of range`, where overflow is
checked: the interpreter (`myla run`), `myla build --checked`, and `myla test`
interpreted and natively. A plain `myla build` wraps (D4), and the
`wrapping_*` methods wrap everywhere. On every target (MYLA_TEST_TARGET)."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import (CAN_BUILD_NATIVE, SKIP_REASON, TEST_TARGET, run_argv, selfhost_run, target_flags,
                                write_program)
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_RUN_MJS = os.path.join(os.path.dirname(STDLIB_ROOT), "tools", "wasm", "run.mjs")

# Each case: the operand type, the operator's expression of `a` and `b`, the
# arguments, what a plain build prints (the wrapped value), and the message.
# The expression is the body of `f(a: T, b: T) -> T`, on line 2 at column
# `12 + col`, where `col` is the operator's offset in it.
OVER = "integer overflow"
SHIFT = "shift amount out of range"
CASES = {
    "add_int32": ("int32", "a + b", 2, "2147483647, 1", "-2147483648", OVER),
    "sub_int32": ("int32", "a - b", 2, "-2147483648, 1", "2147483647", OVER),
    "mul_int32": ("int32", "a * b", 2, "65536, 65536", "0", OVER),
    "neg_int32": ("int32", "-a + b", 0, "-2147483648, 0", "-2147483648", OVER),
    "div_int32": ("int32", "a / b", 2, "-2147483648, -1", "-2147483648", OVER),
    "add_uint8": ("uint8", "a + b", 2, "255, 1", "0", OVER),
    "sub_uint8": ("uint8", "a - b", 2, "0, 1", "255", OVER),
    "mul_uint16": ("uint16", "a * b", 2, "256, 256", "0", OVER),
    "mul_uint32": ("uint32", "a * b", 2, "4294967295, 4294967295", "1", OVER),
    "neg_uint32": ("uint32", "-a + b", 0, "1, 0", "4294967295", OVER),
    "add_int64": ("int64", "a + b", 2, "9223372036854775807, 1", "-9223372036854775808", OVER),
    "sub_int64": ("int64", "a - b", 2, "-9223372036854775807 - 1, 1", "9223372036854775807", OVER),
    "mul_int64": ("int64", "a * b", 2, "4294967296, 2147483648", "-9223372036854775808", OVER),
    "mul_int64_minus_one": ("int64", "a * b", 2, "-1, -9223372036854775807 - 1", "-9223372036854775808", OVER),
    "div_int64": ("int64", "a / b", 2, "-9223372036854775807 - 1, -1", "-9223372036854775808", OVER),
    "add_uint64": ("uint64", "a + b", 2, "18446744073709551615, 1", "0", OVER),
    "sub_uint64": ("uint64", "a - b", 2, "1, 2", "18446744073709551615", OVER),
    "mul_uint64": ("uint64", "a * b", 2, "4294967296, 4294967296", "0", OVER),
    "shl_int32": ("int32", "a << b", 2, "1, 32", "1", SHIFT),
    "shr_uint8": ("uint8", "a >> b", 2, "128, 8", "128", SHIFT),
    "shl_negative": ("int32", "a << b", 2, "1, -1", "-2147483648", SHIFT),
}

# Each fits, so it prints the same everywhere: the edges, a `%` of the
# minimum by -1, bits shifted out, and the wrapping methods.
FITS = r"""fun add(a: int32, b: int32) -> int32 {
    return a + b
}

fun rem(a: int64, b: int64) -> int64 {
    return a % b
}

fun shl(a: int32, b: int32) -> int32 {
    return a << b
}

fun main() {
    print(add(2147483646, 1))
    print(add(-2147483647, -1))
    print(rem(-9223372036854775807 - 1, -1))
    print(shl(3, 31))
    let m: int32 = 2147483647
    print(m.wrapping_add(1))
    let z: uint8 = 0
    print(z.wrapping_sub(1))
    let h: uint64 = 14695981039346656037
    print(h.wrapping_mul(1099511628211))
    let n: int64 = -9223372036854775807 - 1
    print(n.wrapping_neg())
    print(n.wrapping_mul(-1))
    var x: int16 = 32767
    x = x.wrapping_add(x)
    print(x)
}
"""
FITS_OUT = "2147483647\n-2147483648\n0\n-2147483648\n-2147483648\n255\n12638153115695167455\n-9223372036854775808\n-9223372036854775808\n-2\n"


def program(ty: str, expr: str, args: str) -> str:
    return (f"fun f(a: {ty}, b: {ty}) -> {ty} {{\n"
            f"    return {expr}\n"
            f"}}\n\n"
            f"fun main() {{\n"
            f"    print(f({args}))\n"
            f"}}\n")


def build_and_run(path: str, checked: bool) -> tuple[str, str, int]:
    with tempfile.TemporaryDirectory() as tmp:
        binary = os.path.join(tmp, "prog")
        cmd = [selfhost_tool("main"), "build", path, "-o", binary, "--stdlib", STDLIB_ROOT, *target_flags()]
        if checked:
            cmd.append("--checked")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"myla build {path} failed:\n{proc.stderr}")
        argv, exe = run_argv(binary, path)
        ran = subprocess.run(argv, executable=exe, capture_output=True, text=True)
        return ran.stdout, ran.stderr, ran.returncode


class TestOverflow(unittest.TestCase):
    def test_what_fits_is_the_same_everywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, FITS)
            self.assertEqual(selfhost_run(path), (FITS_OUT, "", 0))
            if CAN_BUILD_NATIVE:
                self.assertEqual(build_and_run(path, False), (FITS_OUT, "", 0))
                self.assertEqual(build_and_run(path, True), (FITS_OUT, "", 0))

    def test_a_constant_expression_traps_where_it_runs(self):
        # `let` of an overflowing constant expression: folded and wrapped in a
        # plain build, an error at the operator where overflow is checked
        src = "fun main() {\n    let x: int = 2147483647 + 1\n    print(x)\n}\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, src)
            out, err, code = selfhost_run(path)
            self.assertEqual((out, code), ("", 1))
            self.assertTrue(err.startswith(f"runtime error: {OVER}\n  --> {path}:2:29\n"), err)
            if CAN_BUILD_NATIVE:
                self.assertEqual(build_and_run(path, False), ("-2147483648\n", "", 0))
                self.assertEqual(build_and_run(path, True), ("", f"runtime error: {OVER}\n  --> {path}:2:29\n", 1))

    def test_compound_assignment_traps(self):
        src = ("fun main() {\n    var x: uint8 = 250\n    var i = 0\n    while i < 10 {\n"
               "        x += 1\n        i += 1\n    }\n    print(x)\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, src)
            out, err, code = selfhost_run(path)
            self.assertEqual((out, code), ("", 1))
            self.assertTrue(err.startswith(f"runtime error: {OVER}\n  --> {path}:5:"), err)
            if CAN_BUILD_NATIVE:
                self.assertEqual(build_and_run(path, False), ("4\n", "", 0))
                nout, nerr, ncode = build_and_run(path, True)
                self.assertEqual((nout, ncode), ("", 1))
                self.assertEqual(nerr, err.split("\n", 2)[0] + "\n" + err.split("\n", 2)[1] + "\n")

    def test_myla_test_traps_interpreted_and_natively(self):
        src = ("#test(2147483646)[2147483647]\n"
               "#test(2147483647)[panic(\"integer overflow\")]\n"
               "fun next(n: int) -> int {\n    return n + 1\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, src)
            runs = [[]] + ([["--native", *target_flags()]] if CAN_BUILD_NATIVE else [])
            env = dict(os.environ)
            if TEST_TARGET == "wasm32-wasi":
                env["MYLA_EMULATOR"] = f"node {_RUN_MJS}"
            for flags in runs:
                proc = subprocess.run([selfhost_tool("main"), "test", path, "--stdlib", STDLIB_ROOT, *flags],
                                      capture_output=True, text=True, env=env)
                self.assertEqual(proc.returncode, 0, f"{flags}: {proc.stdout}{proc.stderr}")
                self.assertIn("2 passed", proc.stdout, f"{flags}: {proc.stdout}")


def _make(name: str, case):
    ty, expr, col, args, wrapped, msg = case

    def test(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, program(ty, expr, args))
            where = f"  --> {path}:2:{12 + col}"
            out, err, code = selfhost_run(path)
            self.assertEqual((out, code), ("", 1), err)
            self.assertTrue(err.startswith(f"runtime error: {msg}\n{where}\n"), err)
            if not CAN_BUILD_NATIVE:
                self.skipTest(SKIP_REASON)
            self.assertEqual(build_and_run(path, False), (wrapped + "\n", "", 0))
            self.assertEqual(build_and_run(path, True), ("", f"runtime error: {msg}\n{where}\n", 1))
    return test


for _name, _case in CASES.items():
    setattr(TestOverflow, f"test_{_name}", _make(_name, _case))


if __name__ == "__main__":
    unittest.main()
