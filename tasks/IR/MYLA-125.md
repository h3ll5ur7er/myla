---
id: MYLA-125
title: Instruction selection follow-ups in the IR backend
type: improvement
status: in-progress
priority: medium
labels: [ir, codegen, selfhost, performance]
---
Left over from [[MYLA-121]]; each measured on the compiler compiling itself and the stress programs, kept only if it pays.

- [ ] A division or remainder by a constant other than 0 and −1 skips the zero and −1 tests (`emit_int_op`)
- [ ] A value loaded into a temporary that lives in a register goes straight there (`load`, `load [%p + off]`), not through `%rax` and a held-back store, when the next instruction doesn't take it from `%rax`
