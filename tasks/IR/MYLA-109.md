---
id: MYLA-109
title: IR: later backends and an IR interpreter
type: feature
status: backlog
priority: low
labels: [ir, codegen, selfhost]
---
After [[MYLA-107]]: an LLVM backend on the IR ([[MYLA-62]]), and an IR interpreter if bugs call for one ([[Architecture/IR]], decision 7).

- [ ] Decide when the IR is stable
- [ ] A register allocator over temporaries and locals, with liveness across blocks (a callee-saved-registers-for-scalar-locals version didn't pay off on the compiler, [[MYLA-108]])
- [ ] Retain/release left out for a copy that neither it nor its original writes while both live (needs alias and liveness analysis, [[MYLA-108]])
