# std.int

Methods on every integer type, `int8` to `int64` and `uint8` to `uint64` ([[MYLA-322]]): the arithmetic helpers, the bit counts ([[MYLA-376]]), the checked, saturating and overflowing forms of the operators, and modular arithmetic. The wrapping forms of `+`, `-`, `*` and unary `-` are the language's own methods (D175), in every module whether it imports this one or not. The names and meanings are Rust's (D164 (4)). [[MYLA-320]] will import the module into every program; until then a program writes `import std.int`. It imports nothing itself.

```myla
import std.int

fun main() {
    let x: int8 = 120
    match x.checked_add(10) {
        Some(v) => print(v)
        None => print("overflow")
    }
    print(x.wrapping_add(10))
    print(x.saturating_add(10))
    let (v, over) = x.overflowing_add(10)
    print(f"{v} {over}")
    print((-7).rem_euclid(3))
    print(2.pow(10))
    print(12.gcd(18))
    print(f"{0x50u8.count_ones()} {0x50u8.leading_zeros()} {0x50u8.trailing_zeros()}")
    let p: int64 = 9223372036854775783
    print((p - 1).mulmod(p - 1, p))
    print(3i64.powmod(p - 1, p))
    match 3.modinv(7) {
        Some(inv) => print(inv)
        None => print("no inverse")
    }
}
// output:
// overflow
// -126
// 127
// -126 true
// 2
// 1024
// 6
// 2 1 4
// 1
// 1
// 5
```

`T` is the receiver's type; both operands have it, as the operators want (D4).

| Method | Result |
| --- | --- |
| `abs()`, `signum()` | Signed types only. The absolute value (the minimum has none: it overflows, as `-` does); -1, 0 or 1 |
| `min(other)`, `max(other)` | The smaller, the larger |
| `clamp(lo, hi)` | The number held to `lo` … `hi`; `lo > hi` is a runtime error |
| `pow(exp: uint32)` | The power, multiplied as `*` does: past the width it overflows |
| `gcd(other)`, `lcm(other)` | Never negative; a signed `gcd` of 2^(bits-1) (`MIN.gcd(0)`) overflows; `0.gcd(0)` and an `lcm` with 0 are 0; an `lcm` past the width overflows as `*` does |
| `div_euclid(other)`, `rem_euclid(other)` | Euclidean division: `self == q * other + r` with `r` from 0 to one less than the size of `other`, so `(-7).rem_euclid(3)` is 2 where `-7 % 3` is -1. `MIN.div_euclid(-1)` overflows, as `/` does. For unsigned types `/` and `%` |
| `count_ones() -> int` | The number of bits set; a negative number's bits are its two's complement's, so `(-1i8).count_ones()` is 8 |
| `leading_zeros() -> int`, `trailing_zeros() -> int` | The zero bits above the highest one set, below the lowest one: the width for 0, `leading_zeros` 0 for a negative number. `0x50u8.leading_zeros()` is 1, its `trailing_zeros()` 4 |
| `checked_add`, `checked_sub`, `checked_mul`, `checked_pow` | `Some(result)`, or `None` if it doesn't fit |
| `checked_div`, `checked_rem` | `None` for a divisor of 0, and for `MIN / -1` (`MIN % -1` too, as in Rust) |
| `checked_neg()`, `checked_abs()` | `None` for the signed minimum (`checked_abs` signed only); an unsigned `checked_neg` is `Some(0)` for 0, else `None` |
| `wrapping_pow` | Modulo 2^bits |
| `wrapping_add`, `wrapping_sub`, `wrapping_mul`, `wrapping_neg` | Modulo 2^bits: builtin methods of every integer type, not this module's (D175); one instruction natively, never checked |
| `saturating_add`, `saturating_sub`, `saturating_mul`, `saturating_pow` | The bound the result passes, if it doesn't fit |
| `overflowing_add`, `overflowing_sub`, `overflowing_mul`, `overflowing_neg`, `overflowing_pow` | `(wrapped, overflowed)` |
| `mulmod(other, m)` | `self * other` modulo `m`, from 0 to `m - 1`, without overflow at any width: an `int64` or `uint64` product that would pass 64 bits is done by doubling and adding |
| `powmod(exp: T, m)` | `self` to the power `exp` modulo `m`, from 0 to `m - 1`, without overflow; `exp` not negative |
| `modinv(m) -> Option<T>` | The `x` from 0 to `m - 1` with `self * x` ≡ 1 modulo `m`, or `None` if there is none (`self` and `m` share a divisor); `modinv(1)` is `Some(0)` |

A modulus must be positive: `mulmod`, `powmod` and `modinv` with `m <= 0` are a runtime error (`mulmod: the modulus must be positive, not 0`). A negative `self` or `other` is reduced to its Euclidean remainder first.

## Overflow

An operator whose result doesn't fit its type is the runtime error `integer overflow` where overflow is checked (`myla run`, `myla test`, `myla build --checked`), and wraps in a plain build (D175, [[Language/Expressions-and-operators]]). `pow`, `abs`, `gcd`, `lcm` and `div_euclid`, which overflow as the operators do, are the same: `2.pow(31)` is an error where overflow traps, and -2147483648 in a plain build. The checked, saturating and overflowing ones decide overflow by comparisons that can't overflow, before they compute; the wrapping ones use the builtin `wrapping_*` methods, so none of them traps.

The builtin `wrapping_add`, `wrapping_sub`, `wrapping_mul` and `wrapping_neg` are how code that means to wrap says so: hashes, random generators, checksums. They are the compiler's, not this module's, so that the standard library's own modules, which don't get the implicit ones, can use them without parsing this module's two thousand cases ([[MYLA-396]]), and so that natively each is the one instruction of the plain operator, inlined where it stands.

## How it's written

Myla has no bound that means "an integer type", so `lib/std/int.my` holds one `impl` block per width, generated by `scripts/gen_std_int.py` from one template: change the generator and run it (`--check` tells whether the file is current). Its `#test` cases, 1826 of them, are computed by Python's exact integers, an independent model of every operation, and pass interpreted and natively (`test_std_modules`).
