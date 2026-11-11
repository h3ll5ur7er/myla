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


# The operator traits a generic function's bound names (MYLA-414, H1): the
# cases of CASES whose operator one of them allows run through
# `g<T: Trait>(a: T, b: T) -> T`, whose frame binds `T` to the type.
TRAITS = {"+": "Add", "-": "Sub", "*": "Mul", "/": "Div"}


def generic_program(ty: str, expr: str, args: str) -> str:
    op = expr.split()[1]
    return (f"fun g<T: {TRAITS[op]}>(a: T, b: T) -> T {{\n"
            f"    return {expr}\n"
            f"}}\n\n"
            f"fun f(a: {ty}, b: {ty}) -> {ty} {{\n"
            f"    return g(a, b)\n"
            f"}}\n\n"
            f"fun main() {{\n"
            f"    print(f({args}))\n"
            f"}}\n")


# A sum of a list through `std.list`'s `sum` and `std.iter`'s, whose `+` is
# typed by a type parameter (H1): an `int32` sum past the maximum.
SUMS = {
    "list_sum": "fun main() {\n    let xs = [2000000000, 2000000000]\n    print(xs.sum(0))\n}\n",
    "iter_sum": ("import std.iter as iter\n\nfun main() {\n    let xs = [2000000000, 2000000000]\n"
                 "    print(xs.iter() |> iter.sum(0))\n}\n"),
    "fold": "fun main() {\n    let xs: [uint8] = [200, 100]\n    print(xs.fold(0u8, (a, b) => a + b))\n}\n",
}
SUMS_WRAPPED = {"list_sum": "-294967296", "iter_sum": "-294967296", "fold": "44"}


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


# MYLA-430: a checked 64-bit `+`, `-` and `*` takes the overflow or carry flag
# on x86-64 and aarch64 and a test without flags on wasm32, no division. Each
# case is an operation on operands at the edges (the int32 range wasm32's `*`
# takes a short cut in, the square root of 2^63, the extremes), as a function
# of two operands (`f`), on a variable in place (`x op= b`) and with a
# constant (`a op k`, an immediate on x86-64).
EDGES = {
    "int64": [0, 1, -1, 2, -2, 2147483647, -2147483648, 2147483648, 3037000499, 3037000500, -3037000500, 2 ** 62,
              -2 ** 62, 2 ** 63 - 1, -2 ** 63],
    "uint64": [0, 1, 2, 2 ** 32 - 1, 2 ** 32, 2 ** 63, 2 ** 64 - 1],
}
# fewer for the forms in place (each overflow is a run of its own)
IN_PLACE_EDGES = {"int64": [0, -1, 2, 3037000500, -3037000500, 2 ** 63 - 1, -2 ** 63],
                  "uint64": [0, 1, 2 ** 32, 2 ** 64 - 1]}
EDGE_OPS = ["+", "-", "*", "+=", "-=", "*="]
EDGE_CONSTS = {"int64": [("+", 1), ("-", 1), ("*", 3), ("*", -1), ("+", 2147483647), ("-", -2147483648)],
               "uint64": [("+", 1), ("-", 1), ("*", 3)]}


def _edge_cases() -> list[tuple[str, int, str, int, int]]:
    """Each case: the type, the function's number in the program, the
    operator, and the operands."""
    cases = []
    for ty, values in EDGES.items():
        for k, op in enumerate(EDGE_OPS):
            vs = IN_PLACE_EDGES[ty] if op.endswith("=") else values
            cases += [(ty, k, op, a, b) for a in vs for b in vs]
        for k, (op, c) in enumerate(EDGE_CONSTS[ty]):
            cases += [(ty, len(EDGE_OPS) + k, op, a, c) for a in values]
    return cases


def _edge_literal(ty: str, v: int) -> str:
    # the minimum has no literal: its negation doesn't fit
    return "-9223372036854775807 - 1" if ty == "int64" and v == -2 ** 63 else str(v)


def edge_program() -> str:
    """A program that runs the cases from the one its argument names, printing
    `k result` for each, until one traps."""
    out = []
    for ty in EDGES:
        s = ty[0]
        for k, op in enumerate(EDGE_OPS):
            body = (f"    var x = a\n    x {op} b\n    return x\n" if op.endswith("=")
                    else f"    return a {op} b\n")
            out.append(f"fun {s}{k}(a: {ty}, b: {ty}) -> {ty} {{\n{body}}}\n")
        for k, (op, c) in enumerate(EDGE_CONSTS[ty]):
            literal = str(c) if c >= 0 else f"({c})"
            out.append(f"fun {s}{len(EDGE_OPS) + k}(a: {ty}, b: {ty}) -> {ty} {{\n"
                       f"    return a {op} {literal}\n}}\n")
        n = len(EDGE_OPS) + len(EDGE_CONSTS[ty])
        arms = "\n".join(f"        {k} => {s}{k}(a, b)," for k in range(n))
        out.append(f"fun run_{s}(k: int, a: {ty}, b: {ty}) -> {ty} {{\n"
                   f"    return match k {{\n{arms}\n        _ => a,\n    }}\n}}\n")
    cases = _edge_cases()
    lists = []
    for name, pick in [("ty", lambda c: "0" if c[0] == "int64" else "1"), ("fs", lambda c: str(c[1]))]:
        lists.append(f"    let {name}: [int] = [{', '.join(pick(c) for c in cases)}]")
    for ty in EDGES:
        for name, at in [("a", 3), ("b", 4)]:
            vals = ", ".join(_edge_literal(ty, c[at]) if c[0] == ty else "0" for c in cases)
            lists.append(f"    let {ty[0]}{name}: [{ty}] = [{vals}]")
    out.append("fun main() {\n"
               + "\n".join(lists) + "\n"
               "    var k = num.parse_int(process.args()[1]).unwrap_or(0) as int\n"
               "    while k < ty.len() {\n"
               "        if ty[k] == 0 { print(f\"{k} {run_i(fs[k], ia[k], ib[k])}\") }\n"
               "        else { print(f\"{k} {run_u(fs[k], ua[k], ub[k])}\") }\n"
               "        k += 1\n"
               "    }\n"
               "}\n")
    return "import std.num as num\nimport std.process as process\n\n" + "\n".join(out)


def edge_result(ty: str, op: str, a: int, b: int, wrap: bool) -> int | None:
    """The case's value; None where it overflows and `wrap` is off."""
    r = {"+": a + b, "-": a - b, "*": a * b}[op[0]]
    lo, hi = (-2 ** 63, 2 ** 63) if ty == "int64" else (0, 2 ** 64)
    if lo <= r < hi:
        return r
    if not wrap:
        return None
    r %= 2 ** 64
    return r - 2 ** 64 if ty == "int64" and r >= 2 ** 63 else r


def build_binary(path: str, out: str, checked: bool) -> str:
    binary = os.path.join(out, "prog-checked" if checked else "prog")
    cmd = [selfhost_tool("main"), "build", path, "-o", binary, "--stdlib", STDLIB_ROOT, *target_flags()]
    if checked:
        cmd.append("--checked")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"myla build {path} failed:\n{proc.stderr}")
    return binary


def run_binary(binary: str, path: str, args: list[str]) -> tuple[str, str, int]:
    argv, exe = run_argv(binary, path, args)
    ran = subprocess.run(argv, executable=exe, capture_output=True, text=True)
    return ran.stdout, ran.stderr, ran.returncode


# Functions of each 64-bit operation, for their checked code (MYLA-430).
SHAPES = """fun mul(a: int64, b: int64) -> int64 {
    return a * b
}

fun mulu(a: uint64, b: uint64) -> uint64 {
    return a * b
}

fun add(a: int64, b: int64) -> int64 {
    return a + b
}

fun subu(a: uint64, b: uint64) -> uint64 {
    return a - b
}

fun main() {
    let xs: [int64] = [3, 4]
    let us: [uint64] = [5, 2]
    print(mul(xs[0], xs[1]) + add(xs[0], xs[1]))
    print(mulu(us[0], us[1]) + subu(us[0], us[1]))
}
"""


def function_body(asm: str, name: str) -> str:
    """The lines of the function `myla_<name>` in a target's assembly."""
    lines = asm.splitlines()
    out = []
    for line in lines[lines.index(f"myla_{name}:") + 1:]:
        if line == "\tend_function" or (line.endswith(":") and not line.startswith(".L")):
            break
        out.append(line)
    return "\n".join(out)


class TestOverflow(unittest.TestCase):
    def test_64_bit_edges_trap_where_they_overflow(self):
        # MYLA-430: each case at the edges of int64 and uint64 traps exactly
        # where its value doesn't fit, checked, and wraps in a plain build
        if not CAN_BUILD_NATIVE:
            self.skipTest(SKIP_REASON)
        cases = _edge_cases()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, edge_program())
            plain = build_binary(path, tmp, False)
            want = "".join(f"{k} {edge_result(c[0], c[2], c[3], c[4], True)}\n" for k, c in enumerate(cases))
            self.assertEqual(run_binary(plain, path, ["0"]), (want, "", 0))
            checked = build_binary(path, tmp, True)
            k = 0
            while k <= len(cases):
                out, err, code = run_binary(checked, path, [str(k)])
                for line in out.splitlines():
                    ty, _, op, a, b = cases[k]
                    self.assertEqual(line, f"{k} {edge_result(ty, op, a, b, False)}", f"{ty} {a} {op} {b}")
                    k += 1
                if code == 0:
                    self.assertEqual(k, len(cases), err)
                    break
                ty, _, op, a, b = cases[k]
                self.assertIsNone(edge_result(ty, op, a, b, False), f"{ty} {a} {op} {b} trapped: {err}")
                self.assertEqual((code, err.split("\n")[0]), (1, f"runtime error: {OVER}"))
                k += 1

    def test_64_bit_checks_take_the_flags(self):
        # MYLA-430 (M27): a checked 64-bit `*` divided to find an overflow
        # (std.rt's `mul_overflows_i64`); now the target's flags, or on
        # wasm32 a short cut for operands in the int32 range
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, SHAPES)
            proc = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT, "--checked", "--no-inline",
                                   *target_flags()], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse("mul_overflows" in proc.stdout, "std.rt's division by the operand is called")
        body = {name: function_body(proc.stdout, name) for name in ["mul", "mulu", "add", "subu"]}
        if TEST_TARGET == "aarch64-linux":
            want = {"mul": ["smulh"], "mulu": ["umulh"], "add": ["adds", "cset x12, vc"], "subu": ["subs", "cset x12, cs"]}
        elif TEST_TARGET == "wasm32-wasi":
            want = {"mul": ["i64.shr_u", "i64.div_s"], "mulu": ["i64.shr_u", "i64.div_u"], "add": ["i64.ge_s"],
                    "subu": ["i64.ge_u"]}
        else:
            want = {"mul": ["imulq", "jno"], "mulu": ["mulq", "jno"], "add": ["addq", "jno"], "subu": ["subq", "jnc"]}
        for name, needles in want.items():
            for needle in needles:
                self.assertIn(needle, body[name], f"{name}:\n{body[name]}")
            if TEST_TARGET != "wasm32-wasi":
                self.assertNotIn("div", body[name], f"{name}:\n{body[name]}")

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

    def test_sums_in_generic_code_trap(self):
        # MYLA-414 (H1): `xs.sum(0)` and `iter.sum` add in `std.list`'s and
        # `std.iter`'s generic code, which printed 4000000000 interpreted
        for name, src in SUMS.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                path = write_program(tmp, src)
                out, err, code = selfhost_run(path)
                self.assertEqual((out, code), ("", 1), err)
                self.assertTrue(err.startswith(f"runtime error: {OVER}\n  --> "), err)
                if CAN_BUILD_NATIVE:
                    self.assertEqual(build_and_run(path, False), (SUMS_WRAPPED[name] + "\n", "", 0))
                    nout, nerr, ncode = build_and_run(path, True)
                    self.assertEqual((nout, ncode), ("", 1))
                    self.assertEqual(nerr.split("\n")[0], f"runtime error: {OVER}")

    def test_myla_test_traps_in_generic_code(self):
        # MYLA-414 (H1): `myla test` and `myla test --native` agree on a sum
        # through `std.list`'s generic `sum`
        src = ("#test([2000000000, 2000000000])[panic(\"integer overflow\")]\n"
               "#test([2000000000, 147483647])[2147483647]\n"
               "fun total(xs: [int]) -> int {\n    return xs.sum(0)\n}\n")
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
                self.assertIn("2/2 passed", proc.stdout, f"{flags}: {proc.stdout}")


def _make_generic(name: str, case):
    # MYLA-414 (H1): the operation in a generic function, typed by its type
    # parameter, traps (or wraps, plain) as in a function of the type
    ty, expr, col, args, wrapped, msg = case

    def test(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, generic_program(ty, expr, args))
            where = f"  --> {path}:2:{12 + col}"
            out, err, code = selfhost_run(path)
            self.assertEqual((out, code), ("", 1), err)
            self.assertTrue(err.startswith(f"runtime error: {msg}\n{where}\n"), err)
            if not CAN_BUILD_NATIVE:
                self.skipTest(SKIP_REASON)
            self.assertEqual(build_and_run(path, False), (wrapped + "\n", "", 0))
            self.assertEqual(build_and_run(path, True), ("", f"runtime error: {msg}\n{where}\n", 1))
    return test


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
    if _case[1].split()[1] in TRAITS and not _case[1].startswith("-"):
        setattr(TestOverflow, f"test_generic_{_name}", _make_generic(_name, _case))


if __name__ == "__main__":
    unittest.main()
