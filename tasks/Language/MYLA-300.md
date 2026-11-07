---
id: MYLA-300
title: "Float printing: the shortest round-trip form by default"
type: improvement
status: review
priority: medium
labels: [floats, printing, decision]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). `print(0.1)` gives `0.10000000000000001`, `print(1e300)` a 301-digit number, `ldexp(1.0, -1074)` 330 characters; `format_float` has the shortest form but `print` and `{}` don't use it. With format specs in place (D139), the shortest round-trip form (Python, Rust, JavaScript) as the default is the obvious next decision; it changes the recorded answers, so it is a decision plus a refresh of the expectations.

- [x] The decision; both runners and every target; the recordings or expectations updated

## Done (2026-11-07)

- D155. `std.rt.float_to_str` (what `print`, `str` and an f-string hole without a spec call, natively and inside the interpreter's own native code) takes the fewest digits, up to 17 (9 for a `float32`), that read back as the value: a binary search over the digit count (more digits, correctly rounded, are never farther), each candidate checked by Clinger's fast path (one exact multiply or divide when the digits fit 2^53 and the exponent ±22) or `std.num.f64_literal_bits` otherwise, and its neighbours in the last place tried too, as the scaling's rounding can be one off. Plain digits from 1e-4 up to 1e16, the digits and an exponent outside (`1.5e-7`, `1e300`).
- `test_float_print`: 340 values (edge cases, random bit patterns, random magnitudes, 72 float32s) checked against Python's shortest repr laid out by those rules, interpreted and natively. 200,000 values printed: every one reads back and is the shortest; 0.27 s against the 17-digit version's 0.07 s on values that mostly need 16 or 17 digits (a linear search with the exact parser took 15 s).
- The recordings: 9 answers of the Python toolchain (`interpret`, `selfhost_interp.run`, `selfhost_codegen.run`), 2 of `unit_programs.json` and the hard expectations of `test_compiler_parity`, `test_examples_run`, `test_float64`, `test_ir_contract` and `test_packed_lists` were moved to the new text by a script that accepts a change only where every differing token is the same float (as a float64, or as a float32); none was refused. `examples/floats.my`'s comments still show 17 digits: its recorded answers are keyed by its text (MYLA-288).

