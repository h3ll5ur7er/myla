---
id: MYLA-585
title: Floats get methods (an implicit std.float)
type: feature
status: review
priority: high
labels: [stdlib, language]
---
The owner's decision D199 (2026-11-13). Floats have no methods today (`type 'float64' has no method 'abs'`): every operation is a function of `std.math` (`math.sqrt(x)`), which reads inside out in numeric code (`math.sqrt(math.abs(a - b))`) and is `float64` only. Integers got their methods from the implicit `std.int` (D164); floats get theirs the same way.

- An implicit module `std.float`, loaded into every program like `std.int` (`implicit_modules` in [[selfhost/loader.my]]): `impl float64 { … }` and `impl float32 { … }` with the same methods at each width.
- The methods: `abs`, `signum`, `copysign`, `trunc`, `floor`, `ceil`, `round`, `fract`, `min`, `max`, `clamp`, `sqrt`, `cbrt`, `hypot`, `exp`, `ln`, `log2`, `log10`, `log(base)`, `pow(y)`, `powi(n: int32)`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2(x)`, `sinh`, `cosh`, `tanh`, `to_degrees`, `to_radians`, `lerp(b, t)`, `is_nan`, `is_infinite`, `is_finite`, `to_bits`, `total_cmp(o) -> int` (NaN-safe ordering for sorting), `approx_eq(o, eps)`. The free functions `float.from_bits`, `float.nan()`, `float.infinity()` and the constants (`PI`, `TAU`, `E`, …) behind `import std.float as float`.
- `std.math` stays (its functions are the implementation, fdlibm ports bit-identical on every runner); `float32` methods compute in `float64` and round, except where a direct `float32` routine is needed for speed.
- "Operators on floats": floats on either side of the mixed-type operators of [[MYLA-612]] (`2.0 * v`, `v / 2.0`) come with that task.

- [x] Tests first: `#test` cases in `lib/std/float.my`, a burn test that the methods work without an import, interpreted and natively, at both widths
- [x] `lib/std/float.my`, written by hand (the float32 methods are one line each over the float64 ones, so no generator), loaded implicitly (`implicit_modules` in the loader, `tools/embed`'s parsed bodies, `scripts/update-seed.sh`'s whole-module check)
- [x] A program's own method of the same name on `float64` is the usual `duplicate method` with the note naming `std.float`
- [x] Docs: [[Language/Standard-library/Math]], a new `Float` page, [[Language/Types]], the skill (the habits row "Floats have no methods", `reference/stdlib.md`)
- [x] The seed: `std.float` is implicit, so the bootstrap compiles it; update-seed checks it whole

## Evidence

- `lib/std/float.my`: 45 methods on `float64`, the same on `float32` (computed in float64 and rounded; `to_bits`/`from_bits32` from the float64 bits, which hold a float32 exactly, so no new primitive and no seed staging), constants and `nan`, `infinity`, `from_bits`, `from_bits32`. `cbrt`, `sinh`, `cosh`, `tanh` are new (one Newton step after `pow`; series near zero). Its own cases: 69/69, interpreted and `--native`. Three first failed and were kept honest: `81.0.log(3.0)` is 4.000000000000001, `sinh(1)` and `cosh(1)` are 1 and 2 ulps off; the docs say so.
- Tests first: `tests/burn/test_float_methods.py` failed before the module was implicit (`type 'float64' has no method 'sqrt'`), passes after (4/4: interpreted and natively alike, also as a wasm32 module under Node; registered for aarch64 and the target suites).
- Found on the way: `import std.float as float` made the type `float` unusable (`'float' is a module, not a type`), since `int` and `float` aren't keywords. A built-in type's name now stays the type where a type stands (`is_builtin_type_word` in the loader); `float.PI` stays the module's.
- The compiler's cases: loader 148/148, `tools/embed` 14/14. Bootstrap: byte-identical fixed point.
- Docs: [[Language/Standard-library/Float]] (a tested example), [[Language/Standard-library]], [[Language/Modules]], [[Language/Standard-library/Math]], [[Architecture/Module-loader]], [[Development/Conventions]], [[Development/Testing]], the skill.
