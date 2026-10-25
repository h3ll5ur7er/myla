---
id: MYLA-67
title: A mid-level IR between the checker and the code generators
type: improvement
status: backlog
priority: medium
labels: [backend, design, memory]
---
Both native code generators ([[Architecture/Native-backend]], [[Architecture/Self-hosted-compiler]]) translate the checked AST straight into assembly text, with frame layout, reference counting, copy-on-write, drops on every exit path and value layouts decided while emitting instructions. That makes each backend large (5,200 and 6,200 lines), keeps the ownership rules implicit, and would have to be written again for every new backend.

A small IR in between, with explicit temporaries, explicit `retain`/`drop`/`cow_unique`, explicit layouts and basic blocks, would:

- make reference counting checkable in one place (a verifier, or a debug interpreter for the IR) instead of spread over emission code, where bugs like [[MYLA-2]], [[MYLA-3]] and [[MYLA-22]] hide;
- shrink each backend to instruction selection, so an LLVM backend ([[MYLA-62]]) and a debugger's variable info ([[MYLA-66]]) become much smaller;
- open the door to simple optimisations (reusing frame slots, removing retain/drop pairs).

## Done when

- [ ] An IR design on a wiki page under [[Architecture]]
- [ ] The Python backend lowers through it with identical native output on the parity tests, then the self-hosted backend
