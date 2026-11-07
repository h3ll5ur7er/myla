---
id: MYLA-331
title: "std.num: integers in any radix and width, parse errors"
type: feature
status: backlog
priority: medium
labels: [stdlib, numbers, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #6. `std.num` is used by the compiler (float literals), so its existing functions stay as they are: only new ones are added.

- **Owns:** `lib/std/num.my` (its new functions), `docs/Language/Standard-library/Num.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `parse_int_radix(s, radix) -> Result<int64, ParseIntError>`, the error saying why (empty, a bad digit at an index, out of range); forms for `int32` and `uint64`
- [ ] `to_radix(n, radix)` and `to_hex`, `to_binary`, with an optional width and padding
- [ ] The `int` form of `parse_int` that AoC unwrapped 12 times ([[MYLA-318]]) reads as one call
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
