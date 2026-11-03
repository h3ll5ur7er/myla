---
id: MYLA-160
title: "Backends: de-risking D117"
type: design
status: in-progress
priority: medium
labels: [backend, platforms, design]
---
First step of [[MYLA-62]]. D117 (2026-11-02) chose Myla's own backends from the IR and the runtime in Myla over LLVM. Before the first new backend, the questions that could make that choice expensive are answered with measurements and small prototypes, and recorded on [[Project/Decisions]] (and on [[Architecture/IR]] where they change "Stability"). This replaces the LLVM decision round this task was until then.

- [x] **The gap to C:** benchmarks of Myla native against C at `-O0` and `-O2` (gcc, and clang for what LLVM would win back), and where the time goes ([[MYLA-242]]); no factor fixed in advance: the owner weighs the numbers, the bar being that Myla clearly feels faster than Python. Result ([[Development/Benchmarks]]): about 3× C with Myla's semantics on the geometric mean; clang isn't ahead of gcc; every large gap has a cause and a task ([[MYLA-246]] to [[MYLA-252]]), none needing LLVM
- [ ] **The runtime's port:** the runtime ([[MYLA-162]]) sized piece by piece (allocator, strings, maps, builders, formatting, traps, executor, threads), what Myla can't yet express for it (raw memory, atomics for actor handles, `deep`, `clone` and the executor's queues, D92, thread-local state), and what that costs the language
- [ ] **The IR's open points:** a pointer kind ("Untyped addresses"), sizes per target, 32-bit wasm ("Lowered per target"), SSA form for the optimisations of D117 (3). Options and recommendations: [[MYLA-254]] (with memory widths, which [[MYLA-247]] needs)
- [x] **Calling conventions:** Myla's own convention on each new backend (arguments above the frame base, the callee popping them, [[MYLA-126]]; `become`, D87; suspended frames, D90), and each platform's C convention for the runtime's platform layer and [[MYLA-166]]. Answered by D119 ([[MYLA-250]]): each target's C convention for Myla's own functions too (System V on x86-64, done; AAPCS64, Win64 and wasm's C convention with their backends), the environment a hidden parameter, `become` by `return_call` on wasm and by the checker's stack-word rule natively; floats in vector registers and 16-byte alignment come with the FFI
- [ ] **Object files and linking per platform:** the platform's assembler and linker as external tools, or object files written by Myla (ELF, COFF, Mach-O, wasm modules); signing on macOS
- [ ] **Debug information per platform:** the hand-written DWARF (D82) on Linux and macOS, CodeView/PDB on Windows, wasm's own
- [ ] **The first backend:** wasm (no register allocation; structured control flow rebuilt from the blocks) or aarch64 (closest to x86-64), decided from the answers above
- [ ] **Modularity:** what of the toolchain each backend and platform brings along, and what goes into packages ([[MYLA-245]])
- [ ] **The gates:** how the parity, stress and concurrency suites run on a target the CI machine can't execute (an emulator, a wasm runtime)
