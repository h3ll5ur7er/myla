---
id: MYLA-377
title: "std.num on std.bigint"
type: improvement
status: backlog
priority: low
labels: [stdlib, numbers]
---
Found by the `std.bigint` lane ([[MYLA-345]]). `std.num`'s exact float conversions have big-integer internals of their own, `[uint64]` lists holding 32-bit values. They map almost one to one onto `std.bigint`'s magnitude functions:

| `std.num` | `std.bigint` |
| --- | --- |
| `big_mul_add` | `mag_mul_small` |
| `big_shl`, `big_shr`, `big_cmp`, `big_sub` | `mag_shl`, `mag_shr`, `mag_cmp`, `mag_sub` |
| `big_divmod` (bit by bit, slow) | `mag_divmod` |

Also `big_divmod_small` and `big_to_decimal` (`mag_divmod_small`, `mag_text`), and `big_mul_pow5`/`big_mul_pow10` (a multiply by `pow`).

What it takes:

- [ ] Break the import cycle: `std.fmt` imports `std.num`, and `std.bigint` imports `std.fmt` for its `Format`
- [ ] A magnitude API of `std.bigint` that `std.num` can use (with a bit test), or `BigInt` values
- [ ] The compiler imports `std.num` (`f64_literal_bits`), so a seed (D156); and about 1,400 more lines checked for every program importing `std.num` or `std.fmt`: measure the check time ([[MYLA-359]])
