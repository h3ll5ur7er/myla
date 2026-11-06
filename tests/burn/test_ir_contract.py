"""Burn test: the IR's contract (MYLA-264, Architecture/IR "What each
instruction means"). One program reaches each operation's edge cases: the
minimum divided by -1 at every width, `/` and `%` on negative operands, a
shift's count masked to the width minus one, a negation that wraps, `char`
comparisons, -0 through negation, `sqrt` and `%`, `fmod` with infinities,
`float32` rounding, and the casts that wrap, extend and saturate. Its output is
written down here, as the contract says each value is; the interpreter and
native code give it, on every target (`scripts/test-target.py` runs this
suite)."""
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_source_both_now

PROGRAM = """import std.math as math

// The operands come from lists, so no constant is folded: each operation
// runs as the target does it.
fun div8(a: int8, b: int8) -> str {
    return f"{a / b},{a % b}"
}

fun div16(a: int16, b: int16) -> str {
    return f"{a / b},{a % b}"
}

fun div32(a: int, b: int) -> str {
    return f"{a / b},{a % b}"
}

fun div64(a: int64, b: int64) -> str {
    return f"{a / b},{a % b}"
}

fun main() {
    // the minimum by -1 wraps; `/` toward zero, `%` with the dividend's sign
    let b8: [int8] = [-128, -1, 7, -2]
    let b16: [int16] = [-32768, -1]
    let b32: [int] = [-2147483648, -1, -7, 2]
    let b64: [int64] = [-9223372036854775807 - 1, -1]
    print(f"{div8(b8[0], b8[1])} {div16(b16[0], b16[1])} {div32(b32[0], b32[1])} {div64(b64[0], b64[1])}")
    print(f"{div32(b32[2], b32[3])} {div32(-b32[2], -b32[3])} {div32(b32[2], -b32[3])} {div8(b8[2], b8[3])}")
    // a shift's count masked to the width minus one
    let i8s: [int8] = [-100, 9, 7]
    let u8s: [uint8] = [200, 9, 7]
    let i16s: [int16] = [-3000, 17]
    let u16s: [uint16] = [60000, 17]
    let i64s: [int64] = [-5, 65]
    print(f"{i8s[0] << i8s[1]} {i8s[0] >> i8s[1]} {i8s[0] >> i8s[2]} {u8s[0] >> u8s[1]} {u8s[0] << u8s[2]}")
    print(f"{i16s[0] << i16s[1]} {i16s[0] >> i16s[1]} {u16s[0] >> u16s[1]} {i64s[0] << i64s[1]} {i64s[0] >> i64s[1]}")
    // negation wraps
    print(f"{-b8[0]} {-b16[0]} {-b32[0]} {-b64[0]}")
    // chars compare unsigned, as code points
    let cs = ['a', 'é', '😀', 'Z']
    print(f"{cs[0] < cs[1]} {cs[2] > cs[1]} {cs[3] < cs[0]} {cs[2] as int}")
    // -0: equal to 0, its sign kept by negation and by sqrt
    let zs = [0.0, -1.0, 2.0]
    let nz = -zs[0]
    print(f"{nz == zs[0]} {math.to_bits(nz)} {math.to_bits(math.sqrt(nz))} {math.sqrt(zs[2])} {math.is_nan(math.sqrt(zs[1]))}")
    // fmod: exact, the dividend's sign; infinities
    let inf = zs[2] / zs[0]
    print(f"{zs[2] % inf} {math.is_nan(inf % zs[2])} {-zs[2] % inf} {5.5 % -zs[2]} {-5.5 % zs[2]} {math.to_bits(nz % zs[2])}")
    // float32: each result rounded to its precision
    let fs: [float32] = [16777216.0, 1.0, 0.1]
    print(f"{fs[0] + fs[1]} {fs[2] * fs[2]} {(fs[2] as float) * (fs[2] as float)}")
    // casts: wrapped, extended, saturated
    let ws: [int] = [300, -1, 65535]
    print(f"{ws[0] as int8} {ws[0] as uint8} {ws[1] as uint16} {ws[2] as int16} {ws[1] as uint64} {ws[1] as int64}")
    let fl = [2.5, -2.5, 1e10, -1e10, 0.0]
    print(f"{fl[0] as int8} {fl[1] as int8} {fl[2] as int8} {fl[3] as uint8} {fl[2] as int} {fl[3] as int} {(fl[4] / fl[4]) as int16}")
}
"""

WANT = """-128,0 -32768,0 -2147483648,0 -9223372036854775808,0
-3,-1 -3,1 3,-1 -3,1
56 -50 -1 100 0
-6000 -1500 30000 -10 -3
-128 -32768 -2147483648 -9223372036854775808
true true true 128512
true 9223372036854775808 9223372036854775808 1.4142135623730951 true
2 true -2 1.5 -1.5 9223372036854775808
16777216 0.0100000007 0.010000000298023226
44 44 65535 -1 18446744073709551615 -1
2 -2 127 0 2147483647 -2147483648 0
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class IrContract(unittest.TestCase):
    def test_each_operation_as_the_contract_says(self):
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))


if __name__ == "__main__":
    unittest.main()
