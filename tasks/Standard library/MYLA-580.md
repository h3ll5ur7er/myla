---
id: MYLA-580
title: "math.ldexp takes |k| / 1023 steps: ldexp(1.5, 2147483647) runs 18 seconds interpreted"
type: bug
status: todo
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

- [ ] Clamp the exponent first, as fdlibm's `scalbn` does: past ±2100 the result is the overflow or the underflow whatever `x` is (a finite non-zero double's exponent is within ±1075), so at most three steps run
- [ ] Remove the `ldexp` entry of `SLOW` in `tests/burn/test_generated_extremes.py`, so the suite's sample draws those cases again
