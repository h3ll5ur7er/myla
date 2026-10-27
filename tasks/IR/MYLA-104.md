---
id: MYLA-104
title: IR: aggregates
type: feature
status: backlog
priority: high
labels: [ir, codegen, selfhost]
---
Step 2 of [[MYLA-67]] ([[Architecture/IR]]): structs, tuples and enums without heap values through the IR.

- [ ] Struct and tuple literals, field and tuple-index reads and writes, aggregate locals in slots
- [ ] Enum construction, `match` with patterns, guards and bindings (no heap values yet)
- [ ] Aggregate parameters by address and results through sret, copies
- [ ] The gates with `--ir`; `--ir-stats` up
