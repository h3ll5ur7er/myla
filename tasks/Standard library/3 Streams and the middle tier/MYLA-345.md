---
id: MYLA-345
title: "std.bigint: arbitrary-precision integers"
type: feature
status: backlog
priority: low
labels: [stdlib, numbers, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #14. `std.num` has big-integer internals for its exact float conversions. This makes a public type of them (or a new one, with `std.num` moved onto it).

- **Owns:** `lib/std/bigint.my`, `docs/Language/Standard-library/Bigint.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `BigInt`: add, subtract, multiply (Karatsuba above a size), divide with remainder, `pow`, comparison, parse, print
- [ ] Checked against Python's integers on random operands
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
