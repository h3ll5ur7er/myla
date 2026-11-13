---
id: MYLA-585
title: Floats get methods (an implicit std.float)
type: feature
status: todo
priority: high
labels: [stdlib, language]
---
The owner's decision D197 (2026-11-13). Floats have no methods today (`type 'float64' has no method 'abs'`): every operation is a function of `std.math` (`math.sqrt(x)`), which reads inside out in numeric code (`math.sqrt(math.abs(a - b))`) and is `float64` only. Integers got their methods from the implicit `std.int` (D164); floats get theirs the same way.

- An implicit module `std.float`, loaded into every program like `std.int` (`implicit_modules` in [[selfhost/loader.my]]): `impl float64 { … }` and `impl float32 { … }` with the same methods at each width.
- The methods: `abs`, `signum`, `copysign`, `trunc`, `floor`, `ceil`, `round`, `fract`, `min`, `max`, `clamp`, `sqrt`, `cbrt`, `hypot`, `exp`, `ln`, `log2`, `log10`, `log(base)`, `pow(y)`, `powi(n: int32)`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2(x)`, `sinh`, `cosh`, `tanh`, `to_degrees`, `to_radians`, `lerp(b, t)`, `is_nan`, `is_infinite`, `is_finite`, `to_bits`, `total_cmp(o) -> int` (NaN-safe ordering for sorting), `approx_eq(o, eps)`. The free functions `float.from_bits`, `float.nan()`, `float.infinity()` and the constants (`PI`, `TAU`, `E`, …) behind `import std.float as float`.
- `std.math` stays (its functions are the implementation, fdlibm ports bit-identical on every runner); `float32` methods compute in `float64` and round, except where a direct `float32` routine is needed for speed.
- "Operators on floats": floats on either side of the mixed-type operators of [[MYLA-584]] (`2.0 * v`, `v / 2.0`) come with that task.

- [ ] Tests first: `#test` cases in `lib/std/float.my`, a burn test that the methods work without an import, interpreted and natively, at both widths
- [ ] `lib/std/float.my` (generated per width like `scripts/gen_std_int.py`, if that keeps the two widths in step), loaded implicitly; `test_implicit_imports.py` extended
- [ ] A program's own method of the same name on `float64` is the usual `duplicate method` with the note naming `std.float`
- [ ] Docs: [[Language/Standard-library/Math]], a new `Float` page, [[Language/Types]], the skill (the habits row "Floats have no methods", `reference/stdlib.md`)
- [ ] The seed: `std.float` is implicit, so the bootstrap compiles it; update-seed checks it whole
