---
id: MYLA-551
title: "R9 `--checked` arithmetic: the traps out of line"
type: improvement
status: todo
priority: medium
labels: [codegen, x86-64, aarch64, overflow, performance, round-6]
---
Work package R9 of [[Project/Review-2026-11-12]]. Files: `selfhost/ir_x86.my`, `selfhost/ir_a64.my`. Follows [[MYLA-430]], which is right on 26,155 boundary cases and brought `hot1` from 156 M to 34 M instructions (16 M plain).

By time, a checked int64 loop is still five times slower on x86-64 (user seconds at low load, `repro-r5/native/hot1.my`, `hot4.my`):

| Loop | Plain | Checked | Checked before MYLA-430 |
| --- | --- | --- | --- |
| `hot1` (`*`) | 0.12 | 0.62 | 1.03 |
| `hot4` (`+` and `-` only) | 0.12 | 0.60 to 0.69 | 0.63 to 0.67 |

Each check is a `jno` over an inline `call __trap_overflow`, five taken branches an iteration. The same loop written by hand with `jo` to a trap after the loop takes 0.22 s against 0.55 s (`cold.s` against `inl.s`).

- [ ] `jo` (and aarch64's `b.vs`) to a cold block at the function's end, one per trap site or one per function with the position passed
- [ ] No range check at run time for a constant shift amount (`mov $1; cmp $0x40; jb`)
- [ ] Measured by time on hardware, not only by instructions; the row in Known issues updated
