---
id: MYLA-121
title: Register allocation in the IR backend
type: improvement
status: backlog
priority: medium
labels: [ir, codegen, selfhost, performance]
---
Part of [[MYLA-109]], after [[MYLA-120]]. Temporaries live in frame cells and travel in `%rax` (MYLA-108); a value used again later, or a variable read often (`self`), is reloaded from the frame every time. A first try, the four most-used scalar locals in `%r12`–`%r15`, didn't pay off ([[MYLA-108]]); with operands read where they are ([[MYLA-120]]) a register can be read directly instead of moved to `%rax` first.

- [ ] Liveness of temporaries and scalar slots across blocks (shared with [[MYLA-122]])
- [ ] Temporaries and scalar locals and parameters whose address isn't taken in callee-saved registers (`%rbx`, `%r12`–`%r15`), by linear scan over the liveness intervals, saved in the prologue; not under `-g`
- [ ] Measured on the compiler compiling itself and on the stress programs
