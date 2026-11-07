---
id: MYLA-337
title: std.random and std.uuid
type: feature
status: backlog
priority: medium
labels: [stdlib, random, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #15, #65. A seeded generator is a value: a program that wants reproducible runs seeds it, and one that doesn't seeds it from the OS.

- **Owns:** `lib/std/random.my`, `lib/std/uuid.my`, `docs/Language/Standard-library/Random.md`, `docs/Language/Standard-library/Uuid.md`
- **Needs:** [[MYLA-336]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Rng`: PCG or xoshiro256**, `seeded(n)`, `from_os()`, `next_u64`, `int_in(lo, hi)` without modulo bias, `float`, `bool`, `shuffle`, `choice`
- [ ] `std.uuid`: v4 and v7, parse and print
- [ ] The generator checked against its reference outputs
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
