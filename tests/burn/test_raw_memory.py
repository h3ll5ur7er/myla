"""Burn test: the raw-memory primitives the runtime written in Myla needs
(MYLA-162's prototype, D117).

`__load8`/`__load64`, `__store8`/`__store64`, `__alloc`, `__addr_of`,
`__str_of` and `__copy_bytes` let string concatenation and equality be
written in Myla over a string's cell. Natively, the program prints the same
with the runtime's assembly, with the Myla versions and with the Myla
versions on the bulk copy; the interpreter, which has no raw memory, stops
with an error that says so. A native build's `+` and `==` on strings use
std.rt's versions."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

PROGRAM = """// MYLA-162's prototype: string concatenation and equality written in Myla
// over raw memory, against the runtime's assembly (`+`, `==`).

// `n` bytes from `src` to `dst`, 8 at a time, then the rest.
fun copy_bytes(dst: int64, src: int64, n: int64) {
    var i: int64 = 0
    while i + 8 <= n {
        __store64(dst + i, __load64(src + i))
        i += 8
    }
    while i < n {
        __store8(dst + i, __load8(src + i))
        i += 1
    }
}

// `a + b`: a new cell, its length, then both strings' bytes.
fun concat(a: str, b: str) -> str {
    let pa = __addr_of(a)
    let pb = __addr_of(b)
    let na = __load64(pa)
    let nb = __load64(pb)
    let p = __alloc(na + nb + 8)
    __store64(p, na + nb)
    copy_bytes(p + 8, pa + 8, na)
    copy_bytes(p + 8 + na, pb + 8, nb)
    return __str_of(p)
}

// `a + b` with the bulk copy each backend provides (`__copy_bytes`).
fun concat2(a: str, b: str) -> str {
    let pa = __addr_of(a)
    let pb = __addr_of(b)
    let na = __load64(pa)
    let nb = __load64(pb)
    let p = __alloc(na + nb + 8)
    __store64(p, na + nb)
    __copy_bytes(p + 8, pa + 8, na)
    __copy_bytes(p + 8 + na, pb + 8, nb)
    return __str_of(p)
}

// `a == b`: the lengths, then 8 bytes at a time, then the rest.
fun equal(a: str, b: str) -> bool {
    let pa = __addr_of(a)
    let pb = __addr_of(b)
    let n = __load64(pa)
    if n != __load64(pb) {
        return false
    }
    var i: int64 = 0
    while i + 8 <= n {
        if __load64(pa + 8 + i) != __load64(pb + 8 + i) {
            return false
        }
        i += 8
    }
    while i < n {
        if __load8(pa + 8 + i) != __load8(pb + 8 + i) {
            return false
        }
        i += 1
    }
    return true
}

fun piece(k: int) -> str {
    var sb = StringBuilder()
    for i in 0..k {
        sb.append_byte((97 + i % 26) as uint8)
    }
    return sb.build()
}

fun main() {
    let mode = std_mode()
    let parts = [piece(3), piece(11), piece(24), piece(40), piece(7)]
    var total: int64 = 0
    var same = 0
    for round in 0..40000 {
        let a = parts[round % 5]
        let b = parts[(round * 3 + 1) % 5]
        var s = ""
        var e = false
        if mode == 0 {
            s = a + b
            e = s == b + a
        } else if mode == 1 {
            s = concat(a, b)
            e = equal(s, concat(b, a))
        } else {
            s = concat2(a, b)
            e = equal(s, concat2(b, a))
        }
        total += s.len() as int64
        if e {
            same += 1
        }
    }
    print(total)
    print(same)
}

fun std_mode() -> int {
    let argv = args()
    if argv.len() > 1 && argv[1] == "myla" {
        return 1
    }
    if argv.len() > 1 && argv[1] == "intrinsic" {
        return 2
    }
    return 0
}

from std.process import args
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class RawMemory(unittest.TestCase):
    def test_strings_in_myla_print_what_the_runtime_prints(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "concat.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(PROGRAM)
            exe = os.path.join(tmp, "concat")
            built = subprocess.run([selfhost_tool("main"), "build", path, "-o", exe], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            outs = [subprocess.run([exe, mode], capture_output=True, text=True).stdout
                    for mode in ("asm", "myla", "intrinsic")]
            self.assertEqual(outs, ["1360000\n8000\n"] * 3)
            ran = subprocess.run([selfhost_tool("main"), "run", path, "myla"], capture_output=True, text=True)
            self.assertNotEqual(ran.returncode, 0)
            self.assertIn("raw memory, which only native code does", ran.stderr)


    def test_native_code_concatenates_with_the_runtime_in_myla(self):
        # `+` and `==` on strings call std.rt's functions (MYLA-162; a
        # standard library without std/rt.my gets the embedded one, see
        # test_selfhost_codegen)
        source = 'fun main() {\n    let a = "ab"\n    let b = a + "cd"\n    print(b == "abcd")\n    print(b)\n}\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "plus.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            asm = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT], capture_output=True, text=True,
                                 check=True).stdout
            self.assertIn("call myla_std$rt$str_concat", asm)
            self.assertIn("call myla_std$rt$str_eq", asm)


if __name__ == "__main__":
    unittest.main()
