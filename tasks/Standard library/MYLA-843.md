---
id: MYLA-843
title: "std.num's parse_float takes bignum arithmetic for every number: JSON of `1e-300`s parses a thousand times slower than of strings"
type: bug
status: backlog
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

- [ ] Clinger's fast path in `parse_float`: at most 15 significant digits and a power of ten up to 22 are one exact multiplication or division of float64s (most JSON numbers)
- [ ] Eisel–Lemire (a 128-bit table of powers of five) for the rest, the bignum path only where it can't decide, as Go, Rust and fast_float do
- [ ] `std.num`'s cases for both paths, the halfway points of [[MYLA-795]]'s `long_numbers` among them, and the table above measured again
