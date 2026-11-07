---
id: MYLA-322
title: "std.char and std.int: character classes, integer helpers, checked arithmetic"
type: feature
status: todo
priority: high
labels: [stdlib, integers, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]], roadmap #5, #11, #12, #13. Methods on `char` and on every integer type. A method that is the same for every width is written once per width or, where a bound can carry it, once for all.

- **Owns:** `lib/std/char.my`, `lib/std/int.my`, `docs/Language/Standard-library/Char.md`, `docs/Language/Standard-library/Int.md`
- **Needs:** [[MYLA-319]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `char`: `is_digit`, `is_alpha`, `is_alnum`, `is_space`, `is_upper`, `is_lower`, `to_digit(radix)`, `from_digit`, `to_upper`, `to_lower` (ASCII)
- [ ] Integers: `abs`, `min`, `max`, `clamp`, `sign`, `pow`, `gcd`, `lcm`, `div_euclid`, `rem_euclid`, for every width
- [ ] Checked and wrapping: `checked_add` / `_sub` / `_mul` (an `Option`), `wrapping_*`, `saturating_*`, `overflowing_*`; whatever [[MYLA-311]] decides keeps these
- [ ] Modular: `mulmod` (no overflow on `int64`), `powmod`, `modinv`
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
