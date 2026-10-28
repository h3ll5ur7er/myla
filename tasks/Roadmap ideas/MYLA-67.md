---
id: MYLA-67
title: A mid-level IR between the checker and the code generators
type: improvement
status: review
priority: high
labels: [backend, design, memory]
---
Both native code generators ([[Architecture/Native-backend]], [[Architecture/Self-hosted-compiler]]) translate the checked AST straight into assembly text, with frame layout, reference counting, copy-on-write, drops on every exit path and value layouts decided while emitting instructions. That makes each backend large (5,200 and 6,200 lines), keeps the ownership rules implicit, and would have to be written again for every new backend.

A small IR in between (for the self-hosted backend, D79), with explicit temporaries, explicit `retain`/`drop`/`cow_unique`, explicit layouts and basic blocks, would:

- make reference counting checkable in one place (a verifier, or a debug interpreter for the IR) instead of spread over emission code, where bugs like [[MYLA-2]], [[MYLA-3]] and [[MYLA-22]] hide;
- shrink each backend to instruction selection, so an LLVM backend ([[MYLA-62]]) and a debugger's variable info ([[MYLA-66]]) become much smaller;
- enable optimisations that are impractical on the AST or on assembly text: reusing frame slots instead of one slot per temporary, register allocation for scalars, removing retain/drop pairs that cancel out (most copies of a list that is never written need no reference-count traffic), copy elision for struct returns, constant folding and dead-code elimination after monomorphization (today every non-generic function is emitted), and inlining of small functions and lambdas.

## Design

[[Architecture/IR]], decided as D79 (2026-10-27): the self-hosted backend only (the Python backend stays the reference), three-address code on basic blocks close to the machine with explicit `retain`/`drop`/`cow`, migrated function by function behind `--ir` with a fallback to the current path.

## Steps (epic `IR`)

- [x] The design on [[Architecture/IR]] and D79
- [x] [[MYLA-103]] `ir.my`, the flags, scalar functions through the IR (in review)
- [x] [[MYLA-104]] Aggregates (in review)
- [x] [[MYLA-105]] Heap values, ownership and the verifier (in review)
- [x] [[MYLA-106]] Closures, function values, the remaining constructs, `-g` (in review)
- [x] [[MYLA-107]] The IR by default, the old emission code deleted (in review)
- [ ] [[MYLA-108]] Optimisations
- [ ] [[MYLA-109]] Later: LLVM on the IR, an IR interpreter

## Done when

- [x] An IR design on a wiki page under [[Architecture]]
- [x] The self-hosted backend lowers every function through it, with the same behaviour on the parity tests, the stress tests and the bootstrap ([[MYLA-107]])
