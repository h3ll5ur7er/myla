---
id: MYLA-952
title: "`myla test --native` of a std module: a map keyed by a tuple holding a float32 fails to link (`myla_float64.hash`)"
type: bug
status: todo
priority: low
labels: [native, testing, maps]
---
Found by [[MYLA-969]]: in `lib/std/font.my`, a glyph cache keyed by `(int, float32, int)` made `myla test --native lib/std/font.my` fail at link time with `undefined reference to myla_float64.hash`; the same code built and ran as a program. The module now keys on `px.to_bits()`.

Not reproduced in a program of its own (2026-11-25: a `#test` case with such a map passes `myla test --native` outside `lib/std`), so the trigger is likely how the native test harness loads a std module's implicit `std.float`/`std.hash` impls (a float32 key hashed through float64's impl, D198).

- [ ] A reproduction: a small module under a `--stdlib` directory with such a map and a `#test` case
- [ ] The fix, and the case kept in the suite
