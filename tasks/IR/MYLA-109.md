---
id: MYLA-109
title: IR: later backends and an IR interpreter
type: feature
status: in-progress
priority: low
labels: [ir, codegen, selfhost]
---
After [[MYLA-107]]: better code from the IR first (better binaries in the long run), then an LLVM backend on it ([[MYLA-62]]; the language's design maps onto LLVM directly, so that comes later and isn't urgent), and an IR interpreter if bugs call for one ([[Architecture/IR]], decision 7). The stability decision comes after the optimisations, which may still change the IR.

- [ ] Decide when the IR is stable
- [x] [[MYLA-120]] Instruction selection: compare-and-branch, operands where they are, addressing modes
- [x] [[MYLA-121]] A register allocator over temporaries and locals, with liveness across blocks (a callee-saved-registers-for-scalar-locals version didn't pay off on the compiler, [[MYLA-108]])
- [ ] [[MYLA-122]] Retain/release left out for a copy that neither it nor its original writes while both live (needs alias and liveness analysis, [[MYLA-108]])
