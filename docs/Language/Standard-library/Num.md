# std.num

Numbers from text and back ([[MYLA-79]]). The conversions are exact, computed with big integers, so every implementation gives the same result; the self-hosted compiler converts its float literals with the same code.

| Function | Result |
| --- | --- |
| `parse_int(s: str) -> Option<int64>` | A decimal integer with an optional `-`; `None` for anything else or out of range |
| `parse_float(s: str) -> Option<float64>` | The nearest double to `-? digits (. digits)? ([eE] [+-]? digits)?`; too large is infinite |
| `format_float(x: float64) -> str` | The shortest decimal that reads back as `x`, as Python's `repr` writes it: `1.0`, `0.1`, `1e+16`, `1.5e-07`, `-0.0`, `nan`, `inf` |
| `format_fixed(x: float64, prec: int32) -> str` | `x` with `prec` digits after the point, rounded on its exact binary value, ties to even: `2.67` for `(2.675, 2)` (D139) |
| `pow2(k: int32) -> float64` | 2^k exactly, for -1022 <= k <= 1023 |
| `f64_literal_bits(text) -> uint64`, `f32_round_bits(bits) -> uint64`, `float_from_bits(bits) -> float64` | The bit-level steps (for the compiler) |

`format("{}", x)` writes a float as `print` does, in its shortest round-trip form (`0.1`, `1e300`, D155); `format_float` is Python's `repr` of it (`1.0`, `1e+300`).
