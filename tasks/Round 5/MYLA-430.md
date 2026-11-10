---
id: MYLA-430
title: "P16 --checked 64-bit arithmetic with the overflow flag"
type: improvement
status: todo
priority: medium
labels: [codegen, overflow, performance, round-5]
---
Work package P16 of [[Project/Review-2026-11-09]] (wave B, after [[MYLA-415]]). M27: a checked 64-bit `*` divides to detect overflow, three to five times slower in hot loops.

- [ ] The overflow flag (`jo`, `jc`; aarch64's flags; wasm32's wide multiply) instead of the division, through the IR's check
- [ ] On the three back ends, with the overflow tests and the checked benchmarks before and after
