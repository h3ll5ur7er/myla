---
id: MYLA-67
title: A mid-level IR between the checker and the code generators
type: improvement
status: backlog
priority: high
labels: [backend, design, memory]
---
Both native code generators ([[Architecture/Native-backend]], [[Architecture/Self-hosted-compiler]]) translate the checked AST straight into assembly text, with frame layout, reference counting, copy-on-write, drops on every exit path and value layouts decided while emitting instructions. That makes each backend large (5,200 and 6,200 lines), keeps the ownership rules implicit, and would have to be written again for every new backend.

A small IR in between, with explicit temporaries, explicit `retain`/`drop`/`cow_unique`, explicit layouts and basic blocks, would:

- make reference counting checkable in one place (a verifier, or a debug interpreter for the IR) instead of spread over emission code, where bugs like [[MYLA-2]], [[MYLA-3]] and [[MYLA-22]] hide;
- shrink each backend to instruction selection, so an LLVM backend ([[MYLA-62]]) and a debugger's variable info ([[MYLA-66]]) become much smaller;
- enable optimisations that are impractical on the AST or on assembly text: reusing frame slots instead of one slot per temporary, register allocation for scalars, removing retain/drop pairs that cancel out (most copies of a list that is never written need no reference-count traffic), copy elision for struct returns, constant folding and dead-code elimination after monomorphization (today every non-generic function is emitted), and inlining of small functions and lambdas.

## Done when

- [ ] An IR design on a wiki page under [[Architecture]]
- [ ] The Python backend lowers through it with identical native output on the parity tests, then the self-hosted backend
