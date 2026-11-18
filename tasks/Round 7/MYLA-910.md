---
id: MYLA-910
title: "A subnormal float prints a farther candidate of its shortest digits than Python's repr"
type: bug
status: backlog
priority: low
labels: [runtime, numerics, round-7]
---
Found by [[MYLA-849]]'s differential test against Python's `repr`. A float prints in the fewest digits that read back (D155), and repr writes the nearest of those; `float_to_str` (`lib/std/rt.my`) writes the first of the rounded scaled value and its neighbours that reads back, and for some subnormals that rounded value is a unit off, though not near a tie:

```myla fragment
import std.float as float

fun main() {
    print(float.from_bits(769135236653079u64))  // 3.800032974362634e-309, repr 3.800032974362635e-309
    print(float.from_bits(198124887009477u64))  // 9.78867002575612e-310, repr 9.78867002575613e-310
}
```

Both texts read back as the float, so the output is a shortest round trip, but the first is 0.77 of a unit in the last digit from the float's exact value and repr's 0.23 (the second: 0.52 and 0.48). The same in the interpreter and natively, before and after [[MYLA-849]]. In [[MYLA-849]]'s corpora: 7 of 200,000 floats read from random decimals (about 12,000 of them subnormal), and none of 400,000 normal floats of random bits or of the 8,238 powers of two and their neighbours. Since [[MYLA-849]] `std.num.format_float` writes `print`'s digits, so it differs from repr there too (it rounded the exact decimal before, and gave these right, but 17 digits for 46 of the powers of two).

The scaled value comes from `fscale`'s double-double product, which for these is about 0.3 of a unit off: probably a step that loses the low part for a subnormal (scaled by 10^200 first, then by the rest); not confirmed.

- [ ] A test first: the floats above, and the subnormals of a random corpus, against repr (`tests/burn/test_float_print.py`)
- [ ] `decimal_digits` exact for subnormals (scale `x` by 2^64 first, which is exact, and fold 2^-64 into the power of ten), or the nearest candidate chosen exactly where two read back
- [ ] A decision row if the owner wants D155's "fewest digits" to say "the nearest of them", as repr, Ryū and Schubfach give

Files: `lib/std/rt.my` (`fscale`, `decimal_digits`, `digits_reading_back`).
