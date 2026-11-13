---
id: MYLA-580
title: "math.ldexp takes |k| / 1023 steps: ldexp(1.5, 2147483647) runs 18 seconds interpreted"
type: bug
status: review
priority: low
labels: [std, math, performance]
---
Found by [[MYLA-555]]'s extreme-argument burn test (`tests/burn/test_generated_extremes.py`, the review's `repro-r5/std/gen.py`). `std.math.ldexp` (`lib/std/math.my`) scales by 2^1023 or 2^-1022 in a loop until the exponent fits, so `k = 2147483647` takes about 2.1 million multiplications: 12 ms natively, 18 s under `myla run`, where the review's harness and the burn test's time limit stop it. The answer is right (`inf`, `0`).

```myla
import std.math as math

fun main() {
    print(f"{math.ldexp(1.5, 2147483647)} {math.ldexp(1.5, -2147483647 - 1)}")
}
// output:
// inf 0
```

- [x] Clamp the exponent first, as fdlibm's `scalbn` does: past ±2100 the result is the overflow or the underflow whatever `x` is (a finite non-zero double's exponent is within ±1075), so at most three steps run
- [x] Remove the `ldexp` entry of `SLOW` in `tests/burn/test_generated_extremes.py`, so the suite's sample draws those cases again

## Evidence

`ldexp` ([[lib/std/math.my]]) clamps `k` to ±2100 before its loops (`var n = if k > 2100 { 2100 } else if k < -2100 { -2100 } else { k }`): a finite non-zero double is at least 2^-1074 and less than 2^1024, so from 2099 on the result is the overflow and from -2100 on (2^1024 · 2^-2100 = 2^-1076, below half the least subnormal) the underflow, whatever `x`; zero, the infinities and NaN are themselves at any scale. The loops then take at most two steps and the last multiplication a third.

- **Before.** The task's program and three more lines (`ldexp(1.5, -1074)`, the least subnormal to 2097 and 2098, the greatest double to -2098 and -2097, zero, infinity and NaN to the extremes, 3.0 to ±2100), `myla run`: 42.2 s (on a machine shared with five lanes).
- **After.** The same program, the same output byte for byte (`inf 0 -0` / `1e-323 8.98846567431158e307 inf` / `5e-324 1e-323 0` / `inf nan inf 0`), in 0.023 s. New cases of `ldexp`: the least subnormal to 2^1023, the greatest double to the least subnormal (the edges the clamp must not touch), and `(5e-324, 2147483647)` and `(1.797e308, -2^31)`, which ran 2.1 million steps each: `build/myla test lib/std/math.my --stdlib lib` 55/55, also `--native` (checked), `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node).
- **The burn test.** The `ldexp` entry of `SLOW` is gone from `tests/burn/test_generated_extremes.py`. The 24 `num` cases it held and the 30 `seq` cases of a million characters of padding ([[MYLA-546]]'s box, the next entry, also removed) run on all three runners in 10.3 s and 5.0 s, every answer the same, none near the 20 s limit (a scratch driver over `_gen_extreme` and `_differential`). `tests.burn.test_generated_extremes`: see [[MYLA-553]]'s evidence for the suites.
- A parity program, `iter_ldexp_and_padding_in_bulk` in `tests/burn/test_compiler_parity.py` (with [[MYLA-553]] and [[MYLA-546]]), prints `inf -0 8.98846567431158e307 5e-324` interpreted, natively and `--checked`.
