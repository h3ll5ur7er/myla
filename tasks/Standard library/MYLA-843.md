---
id: MYLA-843
title: "std.num's parse_float takes bignum arithmetic for every number: JSON of `1e-300`s parses a thousand times slower than of strings"
type: bug
status: review
priority: medium
labels: [stdlib, num, json, http, performance]
---
Found by [[MYLA-795]], which made a long number cost what 800 digits cost (H9). Every `parse_float`, std.json's included, goes through `f64_literal_bits`: the digits into a bignum one at a time, a power of ten built by as many multiplications by 10 as the exponent says, and a long division, each step a new list. So an ordinary number costs microseconds, and one with a large exponent tens of them. `http.json_body` hands a request's body to it, so a body of small numbers costs a worker seconds: `1e-300,` repeated is 7 bytes a number.

Measured natively (`json.parse` of a 300 kB array of one item repeated, `[1e-300,1e-300,…]`, 2026-11-18 over 305907a, on a loaded machine):

| Item | 300 kB parsed in |
| --- | --- |
| `"abcdefghi"` | 3 ms |
| `12345` | 9 ms |
| `12345.678` | 231 ms |
| `1.5` | 264 ms |
| `1e-300` | 3,159 ms |

A server's default body limit is 16 MiB: about 170 s of a worker for one body of `1e-300`s, at that rate.

- [x] Clinger's fast path in `parse_float`: at most 15 significant digits and a power of ten up to 22 are one exact multiplication or division of float64s (most JSON numbers)
- [x] Eisel–Lemire (a 128-bit table of powers of five) for the rest, the bignum path only where it can't decide, as Go, Rust and fast_float do
- [x] `std.num`'s cases for both paths, the halfway points of [[MYLA-795]]'s `long_numbers` among them, and the table above measured again

## Evidence

Round 7's follow-ups, Numerics lane, over `3add216`. `std.num` reads a decimal by its first 19 significant digits (`Significand`) and `eisel_lemire`: the 128-bit truncated significand of 10^q from the table `POW10_SIG` (10^-342 to 10^308, in hex, checked entry by entry in big integers by the case `pow10_sig_is_exact`), one 64×64-bit product, a second one where the first's low bits are all ones, as Go's `strconv` has it; it gives up (NO_BITS) near a halfway point. A subnormal result is decided by rounding both ends of the product's error range (`subnormal_bits`, `round_shift`); digits past 19 by reading `w` and `w + 1` alike. Big integers (`big_literal_bits`, the old code) only where those can't decide. `parse_float` takes Clinger's path first (`w < 2^53`, `|q| <= 22`: one exact float64 product or quotient) and no longer copies the text. `f64_literal_bits`, the compiler's, uses the same integer-only path (no float arithmetic, MYLA-29). `u64_bitlen` halves its range instead of looping a bit at a time.

- **Cases**: `std.num` 194 cases before, 252 after (`eisel_lemire`, `subnormal_bits` via `eisel_lemire`, `round_shift`, `round_u64`, `pow10_sig`, `mul_128`, `decimal_bits`, `pow10_sig_is_exact`, and `parse_float`'s and `f64_literal_bits`' new ones: 1 + 2^-53 exactly (to even), a digit above and below it, 0.1's 55-digit exact value, `9007199254740993`, subnormals, `1e309`), all passing interpreted, `--native`, on aarch64 (qemu), wasm32 (Node) and x86_64-windows (Wine); `std.json`'s `long_numbers` (MYLA-795's halfway points) passes.
- **Differential, against Python's `float`**: 300,000 decimals (random of 1 to 25 digits and any exponent, exact halfway points between two float64s and a digit either side of them, perturbed reprs, short ones), and 100,000 subnormal ones (random, halfway points between two subnormals and either side): `parse_float` and `f64_literal_bits` give Python's bits for all of them, 0 differences.
- **`json.parse` of 300 kB of one item repeated**, natively (2026-11-18, over 3add216, a shared machine; [[Language/Standard-library/Num]] keeps the table):

| Item | Before | After |
| --- | --- | --- |
| `"abcdefghi"` | 3 ms | 4 ms |
| `12345` | 10 ms | 9 ms |
| `12345.678` | 259 ms | 7 ms |
| `1.5` | 279 ms | 14 ms |
| `0.30000000000000004` | 148 ms | 5 ms |
| `1e-300` | 3,512 ms | 11 ms |
| `2.5e-320` | 2,914 ms | 11 ms |

- **Suites**: `test_selfhost_floatlit`, `test_json`, `test_float64`, `test_float_print`, `test_float_keys`, `test_toml` pass; the bootstrap reaches its fixed point and `scripts/check-seed.sh` passes.

What still costs: a decimal within about 2^-64 of a halfway point (a crafted one) takes the big integers, whose time grows with the square of its digits; `std.json` bounds them to 800 ([[MYLA-795]]).
