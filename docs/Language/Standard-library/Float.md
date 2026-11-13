# std.float

Methods on `float64` and `float32` (D197, [[MYLA-585]]), as [[Language/Standard-library/Int]] gives the integers theirs: every program sees them without an import (D164), so numeric code reads left to right, `(a - b).abs().sqrt()` rather than `math.sqrt(math.abs(a - b))`. Its constants and free functions need an import, `import std.float as float` (a built-in type's name stays the type where a type stands, so `float` is still the type there). It imports [[Language/Standard-library/Math]], whose functions do the work.

```myla
import std.float as float

fun main() {
    let x = -2.75
    print(f"{x.abs()} {x.floor()} {x.round()} {x.fract()}")
    print(3.0.hypot(4.0))
    print(27.0.cbrt() + 2.0.powi(10))
    print(1.0.atan2(1.0).to_degrees())
    print(2.0.lerp(4.0, 0.25))
    print(float.nan().is_nan())
    var xs = [3.5, -1.0, 0.0, -0.0]
    xs.sort_by((a: float, b: float) => a.total_cmp(b) < 0)
    print(f"{xs[0]} {xs[1]} {xs[2]}")
    let y: float32 = 2.0
    print(f"{y.sqrt()} {y.to_bits():#x}")
}
// output:
// 2.75 -3 -3 -0.75
// 5
// 1027
// 45
// 2.5
// true
// -1 -0 0
// 1.4142135 0x40000000
```

| Group | Methods |
| --- | --- |
| Sign and rounding | `abs`, `signum` (`1.0` or `-1.0` by the sign, a zero's too; NaN for NaN), `copysign(s)`, `trunc`, `floor`, `ceil`, `round` (halves away from zero), `fract` (`x - x.trunc()`) |
| Comparing | `min(o)`, `max(o)` (a NaN gives way to the other), `clamp(lo, hi)`, `total_cmp(o)` (IEEE 754's total order as `-1`, `0`, `1`: `-0.0` before `0.0`, NaN last; for sorting), `approx_eq(o, eps)` |
| Powers and roots | `sqrt`, `cbrt` (exact for a perfect cube), `hypot(o)`, `pow(y)`, `powi(n: int)` (by repeated squaring), `exp`, `ln`, `log2`, `log10`, `log(base)` (`ln(x) / ln(base)`, an ulp or two off where that quotient isn't exact) |
| Trigonometry | `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `y.atan2(x)`, `sinh`, `cosh`, `tanh` (from `exp`, within a few units in the last place), `to_degrees`, `to_radians` |
| Other | `lerp(b, t)` (`self + (b - self) * t`), `is_nan`, `is_infinite`, `is_finite`, `to_bits` (`uint64`, a `float32`'s `uint32`; every NaN's are the one quiet NaN's, D128) |
| Module | `PI`, `TAU`, `E`, `LN2`, `LN10`, `SQRT2`, `EPSILON`, `MAX`, `MIN_POSITIVE`; `nan()`, `infinity()`, `from_bits(b: uint64) -> float64`, `from_bits32(b: uint32) -> float32` |

A `float32` method computes in `float64` and rounds its result: exact for `sqrt` and the rounding methods, within the `float64` function's error for the rest. A program's own method of one of these names on a float is a duplicate naming this module; another name is fine (`impl float64 { fun half(self) -> float64 { … } }`).
