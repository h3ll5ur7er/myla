# std.bigint

Integers of any size ([[MYLA-345]]). A `BigInt` is a sign and a magnitude of 32-bit limbs. It has the operators `+ - * / %` and `< <= > >=`, `==`, a hash, so it can be a map key, and `Format`. It is read and written in any radix from 2 to 36, and big numbers are multiplied, divided, read and written faster than in quadratic time. The module imports [[Language/Standard-library/Fmt]], and std.list (`filled`, `extend`).

```myla
import std.bigint as bigint
from std.bigint import BigInt, ParseBigIntError

fun factorial(n: int) -> BigInt {
    var r = bigint.from_int(1)
    for k in 2..n + 1 {
        r = r * bigint.from_int(k as int64)
    }
    return r
}

fun main() {
    print(factorial(30))
    let big = bigint.from_int(2).pow(100)
    print(f"{big:#x}")
    let n = bigint.parse("-170141183460469231731687303715884105727").unwrap_or(bigint.zero())
    let d = bigint.from_int(1000000007)
    print(f"{n / d} {n % d}")
    print(f"{n.div_floor(d)} {n.mod_floor(d)}")
    print(n < big && big.cmp(n) > 0)
    match bigint.parse("12x4") {
        Ok(v) => print(v)
        Err(e) => print(e)
    }
    var seen: [BigInt: str] = [:]
    seen[big] = "2^100"
    print(seen[bigint.from_int(1).shl(100)])
    print(factorial(1000).to_str_radix(36).len())
}
// output:
// 265252859812191058636308480000000
// 0x10000000000000000000000000
// -170141182269480955845320612798 -639816141
// -170141182269480955845320612799 360183866
// true
// invalid digit at byte 2
// 2^100
// 1650
```

Both operands of an operator are `BigInt`s: `n + 1` is written `n + bigint.from_int(1)`. There is no unary minus on a struct, so `-n` is `n.neg()`.

## Making one

| Function | Result |
| --- | --- |
| `zero() -> BigInt` | Zero |
| `from_int(n: int64) -> BigInt` | `n` |
| `from_uint(n: uint64) -> BigInt` | `n` |
| `parse(s: str) -> Result<BigInt, ParseBigIntError>` | The decimal integer in `s` |
| `parse_radix(s: str, radix: int) -> Result<BigInt, ParseBigIntError>` | The integer written in `s` in `radix` |

The text is an optional `+` or `-` and then one or more digits, of any length. A digit past 9 is a letter, in either case. Leading zeros are allowed, and `-0` is zero. Nothing else is: no spaces, no prefix, no `_`. A radix outside 2 to 36 is a runtime error.

```myla fragment
#derive(Eq)
pub enum ParseBigIntError {
    Empty,              // no digits: "", "-" or "+"
    InvalidDigit(int),  // the byte at this index isn't a digit of the radix
}
```

It has `message()` (`"no digits"`, `"invalid digit at byte 2"`) and implements `Format` with it.

## Arithmetic

| Operator or method | Result |
| --- | --- |
| `a + b`, `a - b`, `a * b` | The sum, difference and product |
| `a / b`, `a % b`, `a.div_rem(b) -> (BigInt, BigInt)` | The quotient rounded toward zero, and the remainder with the sign of `a` |
| `a.div_floor(b)`, `a.mod_floor(b)` | The quotient rounded down, and the remainder with the sign of `b` |
| `a.div_euclid(b)`, `a.rem_euclid(b)` | The quotient and remainder of Euclidean division: the remainder is never negative and less than the size of `b` |
| `a.pow(exp: uint32)` | `a` to the power `exp`; zero to the power 0 is 1 |
| `a.neg()`, `a.abs()` | The other sign, no sign |
| `a.shl(n: int)`, `a.shr(n: int)` | `a * 2^n`, and `a / 2^n` rounded down, as Python's `>>`: -1 shifted right stays -1. A negative `n` is a runtime error |
| `a.signum() -> int`, `a.is_zero()`, `a.is_negative()` | -1, 0 or 1; whether it is zero, below zero |
| `a.bit_len() -> int` | The number of bits of the magnitude, 0 for zero |

`/` and `%` truncate, as they do on Myla's integers ([[Language/Expressions-and-operators]]): `-7 / 2` is -3 and `-7 % 2` is -1. Python's `//` and `%` round down instead, giving -4 and 1: those are `div_floor` and `mod_floor`. Division by zero is a runtime error, `bigint: division by zero`.

## Comparing, hashing, converting

| Operator or method | Result |
| --- | --- |
| `a == b`, `a != b` | Equality (derived: every value has one form) |
| `a < b` and the others, `a.cmp(b) -> int` | The order of the integers (`Ord`) |
| `a.hash(h)` | Derived `Hash`: a `BigInt` can be a map key or a [[Language/Standard-library/Set]] element |
| `a.to_int64() -> Option<int64>`, `a.to_uint64() -> Option<uint64>` | The value, if it fits |
| `a.to_str_radix(radix: int) -> str` | The digits in `radix`, lower case, after a `-` when negative |
| `f"{a}"`, `format("{:>20}", a)` | `Format`: decimal by default |

The format spec is an integer's ([[Language/Standard-library/Fmt]]): fill, alignment (right by default) and width; `+` for the sign of a number that isn't negative; `0` for zeros after the sign; the kinds `x`, `X`, `b` and `o`, with `#` for the prefix `0x`, `0b` or `0o`. A negative number keeps its `-` in every radix (`-ff`), where `format("{:x}", n)` on an `int64` writes its two's complement. A precision is a runtime error.

## How it works

The magnitude is a `[uint32]`, least significant limb first, with no high zero limbs; a product of two limbs and a carry fits a `uint64`. Zero is the empty list and never negative, so every value has exactly one form.

- **Multiplication** is schoolbook while the shorter operand has fewer than 64 limbs, and Karatsuba's above; a square is schoolbook below 128 limbs, where the products of two different limbs are made once. An operand more than twice as long as the other is cut into pieces of the other's length.
- **Division** is Knuth's algorithm D (TAOCP 4.3.1). When the divisor and the quotient both have 80 limbs or more it is Burnikel and Ziegler's recursive division ("Fast recursive division", 1998), which costs a small multiple of a multiplication.
- **Text** is split by divide and conquer on the powers radix^(k·2^i), where radix^k is the largest power of the radix in a limb (10^9 for decimal). Writing divides a number by the power with about half its limbs and writes the quotient and the remainder; reading multiplies the value of the high digits by a power and adds the low ones'. Small pieces, below 40 limbs or 360 digits, are written by repeated division by radix^k and read by repeated multiplication. A radix that is a power of two is read off the bits.

The results were checked against Python's integers on 9,600 random cases natively, 600 of them also interpreted and 3,300 on wasm32: sums, products, the three divisions, powers, comparison, radix conversion both ways and shifts, on operands of 1 to 6,000 digits (dividends of up to 12,000), with zero, both signs, limbs of all ones, divisors next to the dividend and quotients of limbs all ones. The same cases pass with the thresholds set to 2 to 4 limbs and 10 digits, which takes each recursion down to its smallest pieces. The module's cases pin a representative set.

## Speed

Natively, best of 5 runs, on a machine shared with other work (runs vary by about 15 %); Python 3.13 on the same machine for comparison:

| Operation | std.bigint | Python |
| --- | --- | --- |
| Multiplying two 10,000-digit numbers | 0.81 ms | 0.34 ms |
| `pow(3, 100000)` | 3.4 ms | 1.2 ms |
| Dividing a 20,000-digit number by a 10,000-digit one | 2.1 ms | 0.69 ms |
| Reading 100,000 digits | 36 ms | 12 ms |
| Writing 100,000 digits | 85 ms | 25 ms |

Writing by repeated division by 10^9 instead takes 700 ms for 100,000 digits, and reading by repeated multiplication 123 ms; with algorithm D in place of the recursive division, writing takes 355 ms. Karatsuba's threshold is high because each level of it makes several new lists, which cost more in Myla than in C: at 1,024 limbs a product takes 0.72 ms, against 1.63 ms by schoolbook alone.
