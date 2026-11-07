# std.num

Numbers from text and back ([[MYLA-79]], [[MYLA-331]]). Integers are read in any radix from 2 to 36 and for `int32`, `int64` and `uint64`, with a `ParseIntError` that says why a string isn't one; they are written in any radix, hex and binary with a width. The float conversions are exact, computed with big integers, so every implementation gives the same result; the self-hosted compiler converts its float literals with the same code.

```myla
import std.num as num
from std.num import ParseIntError

fun total(text: str) -> Result<int, ParseIntError> {
    var sum = 0
    for part in text.split(",") {
        sum += num.parse_int32(part)?
    }
    return Ok(sum)
}

fun why(e: ParseIntError) -> str {
    return match e {
        Empty => "no digits"
        InvalidDigit(i) => f"not a digit at byte {i}"
        Overflow => "out of range"
    }
}

fun main() {
    print(total("1,2,39").unwrap_or(-1))
    for text in ["1,2x", "1,,2", "1,3000000000", "1_000"] {
        match total(text) {
            Ok(n) => print(n)
            Err(e) => print(why(e))
        }
    }
    print(num.parse_int_radix("-FF", 16).unwrap_or(0))
    print(num.parse_uint64_radix("ffffffffffffffff", 16).unwrap_or(0))
    print(num.to_hex(48879, 8))
    print(num.to_binary(5, 8))
    print(num.to_radix(-255, 36))
}
// output:
// 42
// not a digit at byte 1
// no digits
// out of range
// not a digit at byte 1
// -255
// 18446744073709551615
// 0000beef
// 00000101
// -73
```

A `Result` reads as one call: `?` hands the error to the caller, as `total` does, and `num.parse_int32(s).unwrap_or(0)` gives a default. The methods (`unwrap_or`, `map`, `ok`, `expect`, …) are those of [[Language/Standard-library/Option]].

## Integers from text

| Function | Result |
| --- | --- |
| `parse_int_radix(s: str, radix: int) -> Result<int64, ParseIntError>` | The `int64` written in `s` in `radix` |
| `parse_int32(s: str) -> Result<int32, ParseIntError>` | A decimal `int32` |
| `parse_uint64(s: str) -> Result<uint64, ParseIntError>` | A decimal `uint64` |
| `parse_uint64_radix(s: str, radix: int) -> Result<uint64, ParseIntError>` | The `uint64` written in `s` in `radix` |
| `parse_int(s: str) -> Option<int64>` | A decimal integer with an optional `-`; `None` for anything else or out of range. The older form, kept as it is |

The string is an optional `+` or `-` and then one or more digits. A digit past 9 is a letter, in either case: `a` or `A` is 10, `z` or `Z` is 35. Leading zeros are allowed, and `-0` is zero. Nothing else is: no spaces, no `0x` or `0b` prefix, and no `_` between digits, as Rust allows in literals but not in `parse`. A radix outside 2 to 36 is a runtime error.

The range is exact at both ends: `"-9223372036854775808"` is `int64`'s minimum, and one more in any radix is an `Overflow`. An unsigned form takes a sign too, so `"-0"` is a `uint64` zero, and `"-1"` is out of its range.

```myla fragment
#derive(Eq)
pub enum ParseIntError {
    Empty,              // no digits: "", "-" or "+"
    InvalidDigit(int),  // the byte at this index isn't a digit of the radix
    Overflow,           // the value is out of the type's range
}
```

The first bad byte is the one reported, and a bad digit anywhere wins over an overflow: `"99999999999999999999x"` is an `InvalidDigit(20)`. A second sign is a bad digit: `"--1"` is an `InvalidDigit(1)`.

## Integers to text

| Function | Result |
| --- | --- |
| `to_radix(n: int64, radix: int) -> str` | `n` in `radix`, lower case, with a `-` for a negative one: `to_radix(-255, 16)` is `-ff` |
| `to_radix_u64(n: uint64, radix: int) -> str` | `n` in `radix`, lower case |
| `to_hex(n: uint64, width: int = 0) -> str` | `n` in hex, lower case, with leading zeros up to `width` digits: `to_hex(255, 4)` is `00ff` |
| `to_binary(n: uint64, width: int = 0) -> str` | `n` in binary, with leading zeros up to `width` digits |

A number with more digits than the width keeps them all. There is no prefix: write `"0x" + num.to_hex(n)`. Zero is `0`. A radix outside 2 to 36 is a runtime error. `format("{:x}", n)` and `format("{:08b}", n)` do the same for hex and binary ([[Language/Standard-library/Fmt]]), but write a negative number in two's complement (`ffffffffffffff01` for an `int64` -255), where `to_radix` writes `-ff`.

## Floats

| Function | Result |
| --- | --- |
| `parse_float(s: str) -> Option<float64>` | The nearest double to `-? digits (. digits)? ([eE] [+-]? digits)?`; too large is infinite |
| `format_float(x: float64) -> str` | The shortest decimal that reads back as `x`, as Python's `repr` writes it: `1.0`, `0.1`, `1e+16`, `1.5e-07`, `-0.0`, `nan`, `inf` |
| `format_fixed(x: float64, prec: int32) -> str` | `x` with `prec` digits after the point, rounded on its exact binary value, ties to even: `2.67` for `(2.675, 2)` (D139) |
| `pow2(k: int32) -> float64` | 2^k exactly, for -1022 <= k <= 1023 |
| `f64_literal_bits(text) -> uint64`, `f32_round_bits(bits) -> uint64`, `float_from_bits(bits) -> float64` | The bit-level steps (for the compiler) |

`format("{}", x)` writes a float as `print` does, in its shortest round-trip form (`0.1`, `1e300`, D155); `format_float` is Python's `repr` of it (`1.0`, `1e+300`).

## Speed

`parse_int_radix(s, 10)` reads 10 million decimal strings of 1 to 19 digits in about 315 ms natively, about 32 ns each (best of 7 runs, on a machine shared with other work); `parse_int` takes about 510 ms for the same strings, as it scans each one three times.
