---
id: MYLA-849
title: "Printing a float of a random exponent takes 7 M instructions (M17)"
type: bug
status: review
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

- [x] A test first: the instruction count of printing the 200 random-bit floats, with headroom, and the digits the same as now for a corpus (the shortest that reads back; 17 at most)
- [x] Find the shortest digits without reading them back: Ryū or Schubfach (a table of 128-bit powers of ten, one multiplication for each bound, no big integers), as Rust's, Java's and Go's standard libraries do; or at least a fast path that reads back by the exact parser only when the candidate is within an ulp of the halfway point
- [x] The same in `std.num.format_float` and wherever else a float is written shortest (`std.json`, `std.toml`), and alike in the interpreter (D155: the digits bit for bit)

Files: `lib/std/rt.my` (`float_to_str`, `digits_reading_back`, `reads_back`), `lib/std/num.my` (the Router/JSON lane's number parsing), the interpreter's float printing in `selfhost/`.

## Evidence

Round 7's follow-ups, Numerics lane, over `3add216`. The second box's "at least" option: `float_to_str` keeps its search (the same candidates, in the same order, so the same digits), and `reads_back` reads a candidate back by `std.num.decimal_bits(m, e)`, [[MYLA-843]]'s Eisel–Lemire on the integer and exponent, with no text made; big integers only where the 128-bit product can't decide (within about 2^-64 of a halfway point). Ryū or Schubfach, which would drop the reading back altogether, is [[MYLA-911]]. `f32_round_bits` (a float32's candidates) rounds in a `uint64` (`round_u64`) instead of a big integer. `std.num.format_float` writes `print`'s digits (`f"{x}"`) in Python's layout, as std.rt's `key_float_text` does, so `std.json`, `std.toml`, `std.yaml` and the interpreter's `repr`s write what `print` does. `lib/std/rt.my`: only `reads_back` changed.

- **The tests first** (`tests/burn/test_float_print.py`): `test_random_floats_print_in_few_instructions` prints 200 floats of random bits natively, compares them with Python's repr and counts instructions: 674,605,692 before (failed against its bound), 1,938,819 after (callgrind, 2026-11-18 over 3add216; the program without the floats 440,068), bound 4,000,000. `test_any_exponent_as_python_repr_in_both_runners`: those 200 and a third of the powers of two with the floats either side, `print` and `format_float` in the interpreter and natively, against repr: failed before (`format_float` gave `7.1202363472230444e-307` for 2^-1016, repr `7.120236347223045e-307`), passes after.
- **Print bit for bit** (the differential, `fdiff.my` built before and after): 200,000 floats of random bits, 200,000 with exponents within 2^-60 to 2^60, 200,000 read from random decimals (subnormals among them), 200,000 float32s of random bits, and every power of two with the floats either side (8,238): `print`'s output is byte-identical before and after, natively; 3,000 of each kind interpreted, identical too. Natively the same output on aarch64 (qemu), wasm32 (Node) and x86_64-windows (Wine) for 20,000 of each kind and the powers of two.
- **Against Python's repr**: 0 differences in the random-bit and near-1 kinds and the powers of two; 7 of the 200,000 decimals' floats, all subnormal, print a farther candidate than repr (before and after alike: [[MYLA-910]]). `format_float` before: 46 of the 8,238 powers of two and neighbours differed from repr (17 digits where 16 read back); after: none, and the 7 subnormals of [[MYLA-910]], as `print`.
- **Where the instructions went** (callgrind, the 200 floats): before, `std$num$f64_literal_bits` and its big integers 99.9 %; after, 1.9 M in all: about three quarters reading back (`eisel_lemire`, half of it reading the table's hex digits), the rest `decimal_digits`, `fscale` and the layout.
- **Cases and suites**: `std.num` 252/252 (interpreted, `--native`, aarch64, wasm32, Windows), `std.json` 112/112 (all four), `std.toml`, `std.yaml`, `std.test`, `std.float`, `std.math`; `test_float_print`, `test_float64`, `test_selfhost_floatlit`, `test_json`.
