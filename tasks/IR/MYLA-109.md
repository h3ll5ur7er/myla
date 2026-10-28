---
id: MYLA-109
title: IR: later backends and an IR interpreter
type: feature
status: review
priority: low
labels: [ir, codegen, selfhost]
---
After [[MYLA-107]]: better code from the IR first (better binaries in the long run), then an LLVM backend on it ([[MYLA-62]]; the language's design maps onto LLVM directly, so that comes later and isn't urgent), and an IR interpreter if bugs call for one ([[Architecture/IR]], decision 7). The stability decision comes after the optimisations, which may still change the IR.

- [x] Decide when the IR is stable: now (D85, [[Architecture/IR]], "Stability")
- [x] [[MYLA-120]] Instruction selection: compare-and-branch, operands where they are, addressing modes
- [x] [[MYLA-121]] A register allocator over temporaries and locals, with liveness across blocks (a callee-saved-registers-for-scalar-locals version didn't pay off on the compiler, [[MYLA-108]])
- [x] [[MYLA-122]] Retain/release left out for a copy that neither it nor its original writes while both live (needs alias and liveness analysis, [[MYLA-108]])

## Outcome

- The three optimisations are done: [[MYLA-120]] (−12.1% instructions on the compiler compiling itself, binary −11%), [[MYLA-121]] (wall time −3 to −4%, binary −7%), [[MYLA-122]] (−1.4% instructions); [[MYLA-123]] fixed a bug found on the way. None of them changed the instruction set, which hasn't changed since [[MYLA-106]].
- D85 declares the IR stable: what a backend may rely on, how an instruction is added, and what stays free to change.
- The LLVM backend continues as [[MYLA-62]], whose first step is to decide how it gets the parts outside the IR (the runtime, the walks, the thunks). No bug has called for an IR interpreter so far (decision 7 stands).
