# std.math

Mathematical functions on `float64` ([[MYLA-248]]). Every program also has them as methods of both float types, `x.sqrt()`, `y.atan2(x)`, without an import: [[Language/Standard-library/Float]] (D199). `sqrt` is the processor's correctly rounded square root. The rest is written in Myla after fdlibm (the reference implementation behind most C math libraries), so the interpreter and native code give bit-identical results. `tests/burn/test_math.py` holds each to its stated error against the C library, NaN, the infinities and signed zeros included.

```myla
from std.math import sqrt, sin, atan2, pow, PI

fun main() {
    print(sqrt(2.0))
    print(sin(PI / 2.0))
    print(atan2(1.0, 1.0) * 4.0 == PI)
    print(pow(2.0, 10.0))
}
// output:
// 1.4142135623730951
// 1
// true
// 1024
```

| Function | Result |
| --- | --- |
| `PI`, `TAU`, `E`, `LN2`, `LN10`, `SQRT2` | The constants, rounded to `float64` |
| `sqrt(x)`, `hypot(x, y)` | The square root (correctly rounded); √(x² + y²) without overflow on the way (within 1 ulp) |
| `exp(x)`, `ln(x)`, `log2(x)`, `log10(x)`, `pow(x, y)` | Within 1 ulp; `log2` is exact for powers of two, `log10` for powers of ten up to 10²², `ln(0)` is `-inf`, `ln(-1)` NaN |
| `sin(x)`, `cos(x)`, `atan(x)` | Within 1 ulp, for every finite argument: arguments above 2^20·π/2 are reduced by Payne and Hanek's method |
| `tan(x)`, `asin(x)`, `acos(x)`, `atan2(y, x)` | Within 4 ulp |
| `abs(x)`, `copysign(x, s)`, `trunc(x)`, `floor(x)`, `ceil(x)`, `round(x)` | Exact; `round` takes halves away from zero, zeros keep their sign; `copysign` reads a NaN `s` as positive (D128) |
| `min(a, b)`, `max(a, b)` | The other argument when one is NaN |
| `ldexp(x, k)` | x·2^k, in at most three steps whatever `k` (past ±2100 the result is the overflow or the underflow, as fdlibm's `scalbn` has it, [[MYLA-580]]) |
| `is_nan(x)`, `is_infinite(x)`, `is_finite(x)`, `infinity()`, `nan()` | |
| `to_bits(x) -> uint64`, `from_bits(b) -> float64` | The IEEE 754 bits of a float and back; every NaN gives `0x7FF8000000000000`, so its sign and payload, which differ between processors, can't be seen (D128) |
