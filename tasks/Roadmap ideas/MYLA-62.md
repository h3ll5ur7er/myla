---
id: MYLA-62
title: Optional LLVM backend
type: feature
status: backlog
priority: low
labels: [backend, llvm, design]
---
An optional LLVM backend, to reduce the amount of hand-written assembly to maintain and to get optimisation and other targets for free. The asm backends stay the default and dependency-free.

## Notes

- Emitting **textual LLVM IR** (`.ll`) and running `llc` or `clang` keeps the compiler itself free of dependencies, just as `as`/`ld` are external tools today.
- Both code generators currently go straight from the AST to assembly, with reference counting, copy-on-write and layout logic woven into instruction emission. A second backend would duplicate all of that. A small mid-level IR (explicit temporaries, retains/drops, layouts) shared by the asm and LLVM backends would make the LLVM backend much smaller, and would make the ownership logic, the source of several memory bugs ([[MYLA-2]], [[MYLA-22]]), checkable in one place. See [[MYLA-67]].
- The runtime (allocator, maps, strings, `__run`, float formatting) can stay in Myla or assembly and be linked in, or be emitted as IR.
- Float formatting must stay byte-identical to the interpreter (same operation order; no fast-math).

## Done when

- [ ] Decide IR-first or direct; record it on [[Project/Decisions]]
- [ ] `myla build --backend llvm` passes the native parity tests
