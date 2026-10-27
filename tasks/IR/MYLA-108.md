---
id: MYLA-108
title: IR: optimisations
type: feature
status: backlog
priority: medium
labels: [ir, codegen, selfhost]
---
Step 6 of [[MYLA-67]] ([[Architecture/IR]]): each optimisation a separate change, measured on the compiler compiling itself (time, binary size, peak memory) and checked by the verifier and the gates.

- [ ] Frame slot reuse
- [ ] Retain/drop pairs that cancel (a list copied and never written)
- [ ] Scalars in registers (a simple allocator over temporaries)
- [ ] Copy elision for aggregate results
- [ ] Dead functions after monomorphization
