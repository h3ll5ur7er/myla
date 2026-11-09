---
id: MYLA-311
title: "Decision: integer overflow and the width of int"
type: chore
status: done
priority: medium
labels: [decision, integers, overflow]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F2). `2147483647 + 1` prints `-2147483648` in both runners, with no error. This is D4 (overflow wraps at the operand's width) and D6 (`int` is `int32`), so it is documented. It is also the one finding that can produce a wrong result quietly. No wrong answer got through, but only because the agent used `int64` on purpose. It did wrap once, in an early benchmark, and nobody noticed until the output looked odd.

## Options

- **A. Keep D4 and D6**, and add explicit operations: `wrapping_add`, `checked_add -> Option`, `saturating_add`, so that a program that means to wrap says so. Costs nothing, and changes nothing for code that already works.
- **B. Trap on overflow in the interpreter and in a checked build** (`myla build --checked`, and `myla test`): a runtime error `integer overflow` there, wrapping in a release build (Rust's model). This needs A's explicit operations for hashes and RNGs, which wrap on purpose; `selfhost/` and `lib/std/` use wrapping in hashing, `std.num` and `std.rt`.
- **C. Trap always** (Swift's model): an add, subtract or multiply that overflows is a runtime error on every runner, with `&+`-style or A's explicit operations to wrap. It is the safest option, costs a compare and a branch per operation natively, and needs the most migration.
- **D. `int` is `int64`**: it makes overflow rare instead of loud, and doubles the size of every `int` field and list. It changes D6 and every recording that shows an `int` overflowing.

B or C combines with D, and A is part of every option but D alone.

- [x] The owner's decision, recorded as a D number: D175 (B, `int` stays `int32`)
- [x] Its implementation tasks: [[MYLA-395]]

## Decided (D175, 2026-11-09)

The owner chose B and kept `int` as `int32`: overflow traps in the interpreter, under `myla test` and in `myla build --checked`; a plain build wraps. Code that wraps on purpose uses `std.int`'s `wrapping_*`. Built as [[MYLA-395]].
