---
id: MYLA-374
title: "The native test harness and an enum of one variant"
type: bug
status: review
priority: medium
labels: [testing, native, harness]
---
Found by wave 3's MYLA-342 lane. `myla test --native` ([[MYLA-307]]) compares a case's result with the equality the harness generates. For an enum, that equality matched `b` against the variant of `a` and then `_ => return false`. With one variant the `_` arm is unreachable, which is a type error, so the harness didn't build, and neither did any case whose result contained such an enum (`Result<Grid<char>, GridError>`).

```myla fragment
enum E { Only(int) }

#test(1)[E.Only(1)]
fun f(x: int) -> E { return E.Only(x) }
```

It passed interpreted. Natively: "unreachable match arm (a previous arm already matches everything)".

- [x] `enum_helpers` in [[selfhost/harness.my]] leaves out the `_` arm when the enum has one variant
- [x] A burn test: a one-variant enum, as a result and inside a `Result`, natively the same report as interpreted
- [x] The harness's own cases pass and are run by a burn test, and so are every toolchain file's (`test_selfhost_cases`) (`byte_offset`'s first case expected 9 for the byte offset of `ö`, which is 8: the cases had never been run)

## Evidence

- Test first: `test_an_enum_of_one_variant` failed before the change, and passes after it. `myla test selfhost/harness.my` gave 24/25 before (`byte_offset #1: expected 9, got 8`). The checker counts columns in characters (`let s = "é"; let x: int = "a"` reports column 18), so 8 is right. Now 27/27, with two new cases. `test_the_harness_passes_its_own_cases` runs them.
- `python3 -m unittest tests.burn.test_test_native tests.burn.test_test_functions`: 14 tests OK, before the two harness-case tests were added; both of those pass too.
- `scripts/bootstrap.sh`: byte-identical fixed point (14,322,660 bytes).
- `tests/burn/test_selfhost_cases.py` (new): every file of `selfhost/` and `tools/` with `#test` cases passes them, four files at a time, in 30 s. Nothing ran them before: `test_selfhost_cli`'s corpus skips every toolchain file, since each one has changed since the Python recordings. The first full run found one more stale case, `lower.my`'s `map_lookup` (it counts temporaries, and MYLA-313 added one), which is fixed. All 34 `selfhost/` files and the tools' files pass (checker 633, interp 371, codegen 342, …).
