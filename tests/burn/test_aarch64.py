"""The aarch64 Linux backend (MYLA-163): programs built with `--target
aarch64-linux` (selfhost/ir_a64.my, selfhost/runtime_a64.my and
lib/std/platform_aarch64.my), assembled by clang, linked by ld.lld and run
under qemu-aarch64, give what the same programs built for x86-64 give
(stdout, stderr and the exit code). The x86-64 build is the reference: its
own tests hold it to the interpreter.

Skipped where clang, ld.lld or qemu-aarch64 is missing (CI installs them).
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, native_compiler
from . import test_defer, test_format_specs, test_time, test_unit_type

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

HAVE_A64 = all(shutil.which(t) for t in ("clang", "ld.lld", "qemu-aarch64"))
A64_SKIP = "the aarch64 tests need clang, ld.lld and qemu-aarch64"


@unittest.skipUnless(os.environ.get("MYLA_REQUIRE_TARGETS"), "MYLA_REQUIRE_TARGETS is not set")
class Aarch64Tools(unittest.TestCase):
    """CI sets MYLA_REQUIRE_TARGETS, so a missing tool fails there instead of
    skipping the target's tests unnoticed (MYLA-268)."""

    def test_the_tools_are_there(self):
        self.assertTrue(HAVE_A64, A64_SKIP)

# examples that need what the backend doesn't have yet
NOT_YET: set[str] = set()


def build_x86(src: str, out: str) -> None:
    with open(out + ".s", "wb") as fh:
        subprocess.run([native_compiler(), src, STDLIB_ROOT], stdout=fh, check=True, cwd=_REPO)
    subprocess.run(["as", "--64", "-o", out + ".o", out + ".s"], check=True)
    subprocess.run(["ld", "-o", out, out + ".o"], check=True)


def build_a64(src: str, out: str) -> None:
    with open(out + ".s", "wb") as fh:
        subprocess.run([native_compiler(), src, STDLIB_ROOT, "--target", "aarch64-linux"], stdout=fh, check=True, cwd=_REPO)
    subprocess.run(["clang", "--target=aarch64-linux-gnu", "-c", "-o", out + ".o", out + ".s"], check=True)
    subprocess.run(["ld.lld", "-static", "-o", out, out + ".o"], check=True)


def run(cmd: list[str], stdin: str = "") -> tuple[str, str, int]:
    p = subprocess.run(cmd, input=stdin.encode(), capture_output=True, timeout=120, cwd=_REPO)
    return p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace"), p.returncode


# Programs for what the examples reach little: every integer width's
# wrapping, the traps and their positions, shifts, floats and their casts,
# calls with words on the stack (a `become` too), partial applications with
# a value passed by copy, a map's `remove`.
PROGRAMS = {
    "widths": """
fun main() {
    var a: int8 = 120
    a = a + 10
    var b: uint8 = 250
    b = b + 10
    var c: int16 = 32767
    c = c + 1
    var d: uint16 = 3
    d = d - 4
    var e: uint32 = 0
    e = e - 1
    var f: int64 = 9223372036854775807
    f = f + 1
    var g: uint64 = 0
    g = g - 1
    print(f"{a} {b} {c} {d} {e} {f} {g}")
    let x: int = -7
    var sh = 33
    print(f"{x / 2} {x % 2} {x >> 1} {(x as uint32) >> 28} {x << 29} {x << sh} {x >> sh}")
    let y: uint64 = 18446744073709551615
    print(f"{y / 3} {y % 10} {y > 5}")
    let m: int = -2147483648
    print(f"{m / -1} {m * -1} {-m}")
    print(f"{1 << 31} {1i64 << 33} {255 as int8} {-1 as uint16} {70000 as int16}")
    print(f"{3 & 5} {3 | 5} {3 ^ 5} {~3} {!true}")
}
""",
    "floats": """
fun main() {
    let a = 1.5
    let b = 0.1
    print(f"{a + b} {a - b} {a * b} {a / b} {7.5 % 2.0} {-a}")
    let f: float32 = 0.1
    print(f"{f} {f * 3.0} {f as float}")
    print(f"{3.99 as int} {-3.99 as int} {1e20 as int} {-1e20 as int} {300.5 as uint8} {-5.0 as uint32}")
    let nan = 0.0 / 0.0
    print(f"{nan == nan} {nan != nan} {nan < 1.0} {nan as int} {1.0 / 0.0} {-1.0 / 0.0}")
    print(f"{7 as float / 2.0} {(2 as float) < 3.0} {2.5 <= 2.5} {2.5 >= 3.0}")
    print(f"{18446744073709551615u64 as float} {-1 as float}")
    let big = 1e20
    let tiny: float32 = 5.5
    print(f"{big % 3.0} {-1e300 % 7.25} {-7.5 % 2.0} {1.0 % 0.0} {tiny % 2.0}")
}
""",
    # D128: a NaN's sign and payload can't be seen; every NaN reads as the
    # canonical one (x86-64's 0.0 / 0.0 is 0xFFF8..., aarch64's 0x7FF8...)
    "nan_bits": """
import std.math as math

fun main() {
    let z = 0.0
    let n = z / z
    print(f"{math.to_bits(n)} {math.to_bits(-n)} {math.to_bits(math.sqrt(-1.0))}")
    print(f"{math.copysign(1.0, n)} {math.copysign(1.0, -n)} {math.to_bits(math.abs(-n))}")
    print(f"{math.to_bits(math.from_bits(0xFFF0000000000001u64))} {math.is_nan(math.from_bits(0x7FF0000000000001u64))}")
    print(math.to_bits(math.copysign(n, -1.0)))
}
""",
    "calls": """
fun ten(a: int, b: int, c: int, d: int, e: int, f: int, g: int, h: int, i: int, j: int) -> int {
    return a + 2 * b + 3 * c + 4 * d + 5 * e + 6 * f + 7 * g + 8 * h + 9 * i + 10 * j
}

fun count(n: int, a: int, b: int, c: int, d: int, e: int, f: int, g: int, h: int, acc: int) -> int {
    if n == 0 { return acc + h }
    become count(n - 1, a, b, c, d, e, f, g, h + 1, acc + a)
}

struct P { x: int, y: int, name: str }

fun show(p: P, k: int) -> str {
    return format("{}:{}:{}:{}", p.name, p.x, p.y, k)
}

fun pick(a: str, b: str, c: str) -> str {
    return a + b + c
}

fun main() {
    print(ten(1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
    print(count(100000, 1, 2, 3, 4, 5, 6, 7, 0, 0))
    let p = P { x: 1, y: 2, name: "p" }
    let f = show(p, _)
    print(f(3) + " " + f(4))
    let g = pick("a", _, "c")
    print(g("b"))
    let h = show(_, 9)
    print(h(P { x: 5, y: 6, name: "q" }))
    let fs = [ten, ten]
    print(fs[1](1, 1, 1, 1, 1, 1, 1, 1, 1, 1))
}
""",
    "maps": """
struct V { s: str, xs: [int] }

fun main() {
    var m: [str: V] = [:]
    var i = 0
    while i < 20 {
        m[format("k{}", i)] = V { s: format("v{}", i), xs: [i, i + 1] }
        i = i + 1
    }
    remove(m, "k3")
    remove(m, "k17")
    remove(m, "absent")
    let copy = m
    remove(m, "k0")
    print(f"{m.len()} {copy.len()} {m.contains(\"k3\")} {copy.contains(\"k0\")}")
    for k in m.keys() { print(f"{k} {m[k].s} {m[k].xs[1]}") }
    var n: [int: int] = [1: 10, 2: 20, 3: 30]
    remove(n, 2)
    for k in n.keys() { print(f"{k}={n[k]}") }
}
""",
    "strings": """
fun main() {
    let s = "héllo, wörld"
    var sb = StringBuilder()
    sb.append(s, 0, 3)
    sb.append_byte(33)
    sb.append(format("{}", 42))
    print(f"{sb.build()} {s.len()} {s[1]} {s == \"héllo, wörld\"}")
    var parts: [str] = []
    for w in ["a", "bb", "ccc"] { parts.push(w + w) }
    let last = parts.pop()
    print(f"{parts[0]} {last} {parts.len()}")
}
""",
    "trap_div": """
fun div(a: int, b: int) -> int {
    return a / b
}

fun main() {
    print(div(7, 2))
    print(div(1, 0))
}
""",
    "trap_index": """
fun main() {
    let xs = [1, 2, 3]
    var i = 0
    while i < 5 {
        print(xs[i])
        i = i + 1
    }
}
""",
    "trap_key": """
fun main() {
    let m = ["a": 1]
    print(m["a"])
    print(m["b"])
}
""",
    "panic": """
fun main() {
    print("before")
    panic("stop here")
}
""",
    "exit": """
from std.process import exit

fun main() {
    print("leaving")
    exit(3)
}
""",
}


# the unit type (D138): values without size in lists, maps, enums and tasks
PROGRAMS["unit"] = test_unit_type.PROGRAM
PROGRAMS["void_is_unit"] = test_unit_type.VOID
# format specs (D139): the formatting is std.fmt on every target
PROGRAMS["format_specs"] = test_format_specs.PROGRAM
# `defer` (D135): every way a scope ends, in plain and async functions
PROGRAMS["defer"] = test_defer.PROGRAM

# a struct of some 33 KB: frames, copies and offsets past what one
# instruction reaches
_FIELDS = 4200
PROGRAMS["big"] = (
    "struct Big { " + ", ".join(f"f{i}: int64" for i in range(_FIELDS)) + ", flag: bool, tag: uint8 }\n\n"
    + "fun make(k: int64) -> Big {\n    return Big { " + ", ".join(f"f{i}: k + {i}" for i in range(_FIELDS)) + ", flag: true, tag: 7 }\n}\n\n"
    + "fun total(b: Big) -> int64 {\n    return b.f0 + b.f2100 + b.f4199 + b.tag as int64\n}\n\n"
    + "fun main() {\n    let a = make(3)\n    let b = a\n    var c = b\n    c.f4199 = 1\n    c.tag = 9\n"
    + "    let xs = [a, c]\n    print(f\"{total(a)} {total(c)} {c.flag} {xs[1].tag} {total(xs[0])}\")\n}\n"
)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_A64, A64_SKIP)
class Aarch64Parity(unittest.TestCase):
    def same(self, src: str, stdin: str = "") -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xb, ab = os.path.join(tmp, "x86"), os.path.join(tmp, "a64")
            build_x86(src, xb)
            build_a64(src, ab)
            want = run([xb], stdin)
            got = run(["qemu-aarch64", ab], stdin)
            self.assertEqual(got, want)

    def test_examples(self):
        for path in sorted(glob.glob(os.path.join(_REPO, "examples", "*.my"))):
            name = os.path.splitext(os.path.basename(path))[0]
            if name in NOT_YET:
                continue
            with self.subTest(example=name):
                self.same(path)

    def test_programs(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in PROGRAMS.items():
                with self.subTest(program=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w") as fh:
                        fh.write(source.lstrip())
                    self.same(path)

    def test_compiler(self):
        # the compiler built for aarch64 makes the same assembly as the one
        # built for x86-64, for either target; without --target, for its own
        # (the machine it runs on, D127)
        with tempfile.TemporaryDirectory() as tmp:
            gen = os.path.join(tmp, "gen")
            build_a64("selfhost/gen_main.my", gen)
            for extra, ref in (([], ["--target", "aarch64-linux"]),
                               (["--target", "aarch64-linux"], ["--target", "aarch64-linux"]),
                               (["--target", "x86_64-linux"], [])):
                with self.subTest(target=extra):
                    src = os.path.join(_REPO, "examples", "maps.my")
                    want = run([native_compiler(), src, STDLIB_ROOT] + ref)
                    got = run(["qemu-aarch64", gen, src, STDLIB_ROOT] + extra)
                    self.assertEqual(got[2], 0, got[1])
                    self.assertEqual(got, want)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_A64, A64_SKIP)
class Aarch64Tasks(unittest.TestCase):
    def test_stress_programs(self):
        # the concurrency stress programs (test_concurrency_stress), built
        # for aarch64, on 1, 4 and 16 workers and in the other orders
        from .test_concurrency_stress import EXPECTED, SCHEDULES, _DIR
        for name, want in EXPECTED.items():
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                exe = os.path.join(tmp, name)
                build_a64(os.path.join(_DIR, name + ".my"), exe)
                runs = [{"MYLA_THREADS": w} for w in ("1", "4", "16")]
                runs += [{"MYLA_THREADS": "1", "MYLA_SCHED": sched} for sched in SCHEDULES]
                for extra in runs:
                    p = subprocess.run(["qemu-aarch64", exe], capture_output=True, text=True, timeout=120,
                                       env=dict(os.environ, **extra))
                    self.assertEqual((p.stdout, p.returncode), want, extra)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_A64, A64_SKIP)
class Aarch64StackOverflow(unittest.TestCase):
    # as test_native_runtime's: running out of the main stack or a worker's
    # is a runtime error. qemu-user maps the guest's stack at a fixed size
    # (8 MiB unless QEMU_STACK_SIZE says otherwise) instead of growing it to
    # the limit the program raises, so the first million calls get 130 MB.
    DOWN = ("fun down(n: int) -> int {\n    if n == 0 {\n        return 0\n    }\n"
            "    return down(n - 1) + 1\n}\n\n")

    def run_a64(self, source: str, **env: str) -> tuple[str, str, int]:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "overflow.my")
            with open(path, "w") as fh:
                fh.write(source)
            exe = os.path.join(tmp, "overflow")
            build_a64(path, exe)
            p = subprocess.run(["qemu-aarch64", exe], capture_output=True, text=True, timeout=120,
                               env=dict(os.environ, **env))
            return p.stdout, p.stderr, p.returncode

    def test_the_main_stack(self):
        source = self.DOWN + "fun main() {\n    print(down(1000000))\n    print(down(100000000))\n}\n"
        self.assertEqual(self.run_a64(source, QEMU_STACK_SIZE="130000000"),
                         ("1000000\n", "runtime error: stack overflow\n", 1))

    def test_a_worker_stack(self):
        source = ("import std.task as task\n\n" + self.DOWN
                  + "async fun deep(k: int) -> int {\n    return down(100000000 + k)\n}\n\n"
                  "#main\nasync fun main() {\n    var fs: [async () -> int] = []\n"
                  "    for k in 0..4 {\n        fs.push(async () => await deep(k))\n    }\n"
                  "    let rs = await task.all(fs)\n    print(rs.len())\n}\n")
        for _ in range(5):
            self.assertEqual(self.run_a64(source, MYLA_THREADS="4"), ("", "runtime error: stack overflow\n", 1))


@unittest.skipUnless(HAVE_A64, A64_SKIP)
class Aarch64Time(test_time.Time):
    """test_time's programs (timers, reads that suspend, child processes)
    built for aarch64 and run under qemu (through a script, as the tests run
    the binary)."""

    def test_a_child_process_waited_for_without_blocking_the_worker(self):
        # As test_time's, but on one worker the property, not the exact order:
        # the child's 0.2 s against five 30 ms ticks leaves 50 ms, which qemu's
        # emulated clock reads and polls can use up on a busy machine (one run
        # in the full suite printed the fifth tick after the child's line).
        # A tick before the child's line shows the worker wasn't blocked.
        want = "t\nt\nt\nt\nt\n4 6 3\n5\n200000 200000\nnot found\ntimed out\ntrue\n5\n"
        exe = self.native("process", test_time.PROCESS)
        for workers in ["1", "4"]:
            with self.subTest(workers=workers):
                out, err, code, _ = self.run_timed([exe], MYLA_THREADS=workers)
                self.assertEqual((sorted(out.splitlines()), err, code), (sorted(want.splitlines()), "", 0))
                if workers == "1":
                    self.assertEqual(out.splitlines()[0], "t")

    def native(self, name: str, text: str) -> str:
        exe = os.path.join(self.dir, name)
        build_a64(self.source(name, text), exe + ".a64")
        with open(exe, "w", encoding="utf-8") as fh:
            fh.write(f'#!/bin/sh\nexec qemu-aarch64 "{exe}.a64" "$@"\n')
        os.chmod(exe, 0o755)
        return exe


if __name__ == "__main__":
    unittest.main()
