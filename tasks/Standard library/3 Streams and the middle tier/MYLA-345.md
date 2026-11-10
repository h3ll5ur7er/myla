---
id: MYLA-345
title: "std.bigint: arbitrary-precision integers"
type: feature
status: done
priority: low
labels: [stdlib, numbers, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #14. `std.num` has big-integer internals for its exact float conversions. This makes a public type of them (or a new one, with `std.num` moved onto it).

- **Owns:** `lib/std/bigint.my`, `docs/Language/Standard-library/Bigint.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `BigInt`: add, subtract, multiply (Karatsuba above a size), divide with remainder, `pow`, comparison, parse, print
- [x] Checked against Python's integers on random operands
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- [[lib/std/bigint.my]] and [[Language/Standard-library/Bigint]]. `BigInt` is a sign and a `[uint32]` magnitude (products in `uint64`), `#derive(Eq, Hash)`, with `Add`, `Sub`, `Mul`, `Div`, `Rem`, `Ord` and `Format`; `parse` and `parse_radix` return `Result<BigInt, ParseBigIntError>` (D168: `Empty`, `InvalidDigit(int)`, `message()`, `Format`). `/` and `%` truncate as on Myla's integers; `div_floor`/`mod_floor` are Python's; `div_euclid`/`rem_euclid` as in std.int.
- Algorithms: schoolbook, Karatsuba from 64 limbs (squares from 128); Knuth's algorithm D, Burnikel–Ziegler from 80 limbs of divisor and quotient; text in any radix by divide and conquer on radix^(k·2^i), powers of two read off the bits.
- Tests: 141 cases (139 `#test` cases and 2 test functions, all the module's own), `build/myla test lib/std/bigint.my --stdlib lib` 141/141 interpreted (5.5 s), 141/141 `--native`, 141/141 `--target aarch64-linux`; on `wasm32-wasi` the run stops at the first panic-expecting case (MYLA-370), and the cases without one pass (`--only big`, `calc`, `mag_`). After a bootstrap `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks`: OK (6 tests).
- Against Python 3.13: a generator (random operands of 1 to 6,000 digits, both signs, zero, limbs of 0, 1, 2^31 and 2^32 - 1, divisors next to the dividend or near its root, quotients and divisors of limbs all ones, divisors and quotients past the recursive division's size) wrote 9,600 cases of `+ - *`, the three divisions, `pow`, `cmp`, radix conversion both ways and shifts; a Myla program ran them and its output matched Python's line for line: all 9,600 natively, 600 interpreted, 3,300 on wasm32, and all 9,600 natively again with the thresholds set to 4 limbs and 10 digits (which found a carry past the end in Karatsuba's join, fixed and pinned). Instrumented, the runs reach every correction branch: algorithm D's q̂ fix and add-back, Burnikel–Ziegler's all-ones estimate and its fix-up loop. The pinned cases are Python's values (`calc` exactly; `big_product`, `big_square`, `big_quotient`, `big_text` by digit count and the first and last 15 digits).
- Speed natively, best of 5 (machine shared, ±15 %): 10,000 × 10,000 digits 0.81 ms (pure schoolbook 1.65 ms; Python 0.34 ms); `pow(3, 100000)` 3.4 ms (Python 1.2 ms); 20,000 / 10,000 digits 2.1 ms (algorithm D only: 9.1 ms; Python 0.69 ms); reading 100,000 digits 36 ms (quadratic: 123 ms; Python 12 ms); writing 100,000 digits 85 ms (quadratic: 700 ms; with algorithm D in the divide and conquer: 355 ms; Python 25 ms).


## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
