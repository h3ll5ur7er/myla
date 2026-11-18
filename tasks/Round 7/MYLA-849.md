---
id: MYLA-849
title: "Printing a float of a random exponent takes 7 M instructions (M17)"
type: bug
status: todo
priority: medium
labels: [runtime, numerics, performance, round-7]
---
Filed by [[MYLA-796]] for M17 of [[Project/Review-2026-11-17]] (old): `f"{x}"` of a float64 whose exponent is far from 0 costs millions of instructions, where one near 1 costs a few thousand. The review's `repro-r6/library/float_print_slow.my` measured 6.5 M instructions (1 to 2 ms) for random bits.

Measured on [[MYLA-796]]'s branch (`e659342` plus its changes, which don't touch printing), natively, valgrind's count, 200 floats each:

| Floats | Instructions | Each |
| --- | --- | --- |
| 0.5, 200 times | 0.82 M | (the program) |
| exponents within 2^-60 .. 2^60, 53 random bits | 95.2 M | 0.47 M |
| random bits, any exponent | 1,478.7 M | 7.4 M |

Where they go (callgrind, inclusive): `std$rt$float_to_str` binary-searches the fewest digits that read back (`digits_reading_back` → `reads_back`), and each candidate is read back by `std$num$f64_literal_bits`, the exact parser, in big integers: 1,475.6 M of the 1,477.7 M, in `big_divmod` (1,049 M), `big_shl` (879 M), `big_mul_add`, `big_mul_pow10`, and `list_grow` (614 M) for their lists.

- [ ] A test first: the instruction count of printing the 200 random-bit floats, with headroom, and the digits the same as now for a corpus (the shortest that reads back; 17 at most)
- [ ] Find the shortest digits without reading them back: Ryū or Schubfach (a table of 128-bit powers of ten, one multiplication for each bound, no big integers), as Rust's, Java's and Go's standard libraries do; or at least a fast path that reads back by the exact parser only when the candidate is within an ulp of the halfway point
- [ ] The same in `std.num.format_float` and wherever else a float is written shortest (`std.json`, `std.toml`), and alike in the interpreter (D155: the digits bit for bit)

Files: `lib/std/rt.my` (`float_to_str`, `digits_reading_back`, `reads_back`), `lib/std/num.my` (the Router/JSON lane's number parsing), the interpreter's float printing in `selfhost/`.
