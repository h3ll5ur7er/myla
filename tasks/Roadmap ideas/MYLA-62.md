---
id: MYLA-62
title: Optional LLVM backend, and other platforms through it
type: feature
status: backlog
priority: medium
labels: [backend, llvm, design]
---
An optional LLVM backend, to reduce the amount of hand-written assembly to maintain and to get optimisation and other targets for free. The asm backends stay the default and dependency-free.

## Notes

- Emitting **textual LLVM IR** (`.ll`) and running `llc` or `clang` keeps the compiler itself free of dependencies, just as `as`/`ld` are external tools today.
- Both code generators currently go straight from the AST to assembly, with reference counting, copy-on-write and layout logic woven into instruction emission. A second backend would duplicate all of that. A small mid-level IR (explicit temporaries, retains/drops, layouts) shared by the asm and LLVM backends would make the LLVM backend much smaller, and would make the ownership logic, the source of several memory bugs ([[MYLA-2]], [[MYLA-22]]), checkable in one place. See [[MYLA-67]].
- The runtime (allocator, maps, strings, `__run`, float formatting) can stay in Myla or assembly and be linked in, or be emitted as IR.
- Float formatting must stay byte-identical to the interpreter (same operation order; no fast-math).

- **IR first is settled:** the IR exists and is stable (D79, D85), so this backend starts from it.

## Plan (2026-10-31)

User code through LLVM is mostly mechanical now. What LLVM doesn't give for free is the runtime (hand-written x86-64 assembly) and the platform layer (D2, no libc), so the steps are:

1. [[MYLA-160]] The decision round (D98): how LLVM is reached, the calling convention of user code, a pointer kind, sizes per target, the runtime's future, D2 per target, debug information, the gates
2. [[MYLA-161]] User code on x86-64 Linux through LLVM, linked with the existing assembly runtime: the IR-to-LLVM mapping checked against the parity tests first; debug information with it ([[MYLA-167]])
3. [[MYLA-162]] The runtime off assembly: a portable runtime and a thin platform layer, the step that makes other platforms affordable
4. Targets: [[MYLA-163]] Linux on aarch64, [[MYLA-164]] macOS, [[MYLA-158]] WebAssembly, [[MYLA-165]] Windows
5. [[MYLA-166]] A C FFI, which the GUI ([[MYLA-63]]) needs

## Done when

- [ ] Decide IR-first or direct; record it on [[Project/Decisions]] (IR first: D79, D85; the rest is [[MYLA-160]])
- [ ] `myla build --backend llvm` passes the native parity tests ([[MYLA-161]])
- [ ] At least one target besides x86-64 Linux ([[MYLA-163]] to [[MYLA-165]], [[MYLA-158]])
