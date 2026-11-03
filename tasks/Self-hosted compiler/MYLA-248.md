---
id: MYLA-248
title: "std.math: square root and the other mathematical functions"
type: feature
status: review
priority: medium
labels: [stdlib, floats, runtime]
---
Found while writing the n-body benchmark ([[MYLA-242]]): Myla had no square root, so the benchmark took it by 16 Newton steps in every version. The owner's direction (2026-11-03): a new module, `std.math`, as the home of the mathematical functions (sin, cos, tan, ln, exp and the rest).

- [x] `sqrt` as a primitive: `sqrtsd` natively, the same correctly rounded result in the interpreter
- [x] The exponentials and logarithms, the trigonometric functions and their inverses, `pow`, `hypot`, rounding, `min`/`max`, the classes, bits and constants, with NaN, the infinities and signed zeros as in C
- [x] [[Language/Standard-library]]; the n-body benchmark uses `sqrt` in all its versions

## Evidence

- **Three primitives:**
  - `__sqrt` (`sqrtsd`), `__f64_bits` and `__f64_from_bits` (a move: a float travels as its bits) in the checker, the lowering, the native runtime and the interpreter, which runs them natively.
  - They needed no two-step seed: the compiler itself uses none of them.
- **The module.** `lib/std/math.my` is written in Myla after fdlibm, so the interpreter and native code give bit-identical results:
  - `exp`, `ln`, `log2`, `log10` (exact for powers of two and of ten), `pow`, `hypot`, `sin`, `cos`, `atan` within one unit in the last place;
  - `tan`, `asin`, `acos`, `atan2` within four;
  - `trunc`, `floor`, `ceil`, `round` and `abs` exact;
  - plus `min`, `max`, `copysign`, `ldexp`, `is_nan`, `is_infinite`, `is_finite`, `infinity`, `nan`, `to_bits`, `from_bits`, and `PI`, `TAU`, `E`, `LN2`, `LN10`, `SQRT2`.
- **Three corrections found by the test, each against the C library:**
  - `pow` through `exp(y·ln x)` was tens of units off: it is now a faithful port of fdlibm's `e_pow.c`, with log2 in extra precision and `y` split in two.
  - `sin(1.79e308)` was NaN: arguments above 2^20·π/2 are now reduced by Payne and Hanek's method (fdlibm's `__kernel_rem_pio2`). Its table of 2/π, 1584 bits, is computed from π by Machin's formula, not copied.
  - `hypot` rounded twice: it now scales only where the squares would overflow or underflow, by an exact power of two.
  - fdlibm's own `exp(1)` is one unit above e; a Python run of the same algorithm confirmed the port is faithful (at most one unit from libm over 100,000 inputs).
- **The test first.** `tests/burn/test_math.py` checks every function on about 3,700 inputs:
  - normal ranges, huge arguments for the trigonometric functions, the edges of each domain, NaN, both infinities and both zeros;
  - the interpreter and native code must agree bit for bit, and each result must lie within its documented error of Python's `math` (the C library).
- **Found on the way:** the language server's resolver walked a compound assignment's target twice (`n -= 1023` is `n = n - 1023`), so `--resolve` listed one use twice. `std.math` was the first corpus file to use `-=`. Each use is now recorded once per token; `test_a_compound_assignment_is_one_use` fails without the fix.
- **n-body** with the real `sqrt`: 1,326 ms in the baseline → 264 ms (median of 5), 5× as fast. Its C versions switched to `sqrt` too, so the comparison with them stays like for like ([[Development/Benchmarks]]).
- The bootstrap reaches its fixed point; the burn suite passes.
