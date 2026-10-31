---
id: MYLA-160
title: "LLVM: the decision round (D98)"
type: design
status: todo
priority: medium
labels: [llvm, backend, design]
---
First step of [[MYLA-62]]: the questions the LLVM backend has to settle before any code, put to the owner and recorded as D98 on [[Project/Decisions]] (and on [[Architecture/IR]] where they change "Stability").

- [ ] **How LLVM is reached:** textual `.ll` run through `llc` or `clang` (the compiler stays free of dependencies; LLVM is a build tool like `as` and `ld`), as an optional backend (`myla build --backend llvm`), the assembly backend staying the default and the bootstrap's
- [ ] **Calling convention of user code:** Myla's own stack-based convention (arguments in the argument words above `%rbp`, the callee popping them, [[MYLA-126]]) can't be expressed in LLVM; System V or `fastcc` for user functions, `musttail` for `become` (D87) and for the suspensions of frame functions (D90), and what that means for the hand-written runtime's entry points that call user code (the executor, `__fnval` adapters, thunks)
- [ ] **A pointer kind in the IR:** addresses are `uint64` temporaries today ([[Architecture/IR]], "Untyped addresses"); `inttoptr` works but weakens LLVM's alias analysis
- [ ] **Sizes per target:** sizes and offsets are constants in the IR ("Lowered per target"); lowering again per target, or symbolic sizes resolved by the backend (32-bit wasm, [[MYLA-158]])
- [ ] **The runtime's future:** what moves from hand-written assembly to Myla or LLVM IR, what stays per platform ([[MYLA-162]]), and how atomics (actor handles, `deep`, `clone`, the executor's queues, D92) are expressed there
- [ ] **D2 per target:** no libc stays for Linux; macOS (no stable syscall ABI: libSystem), Windows (its system DLLs) and wasm (host imports) need a system library or imports
- [ ] **Debug information:** LLVM metadata in place of the hand-written DWARF, and how the gdb tests and pretty-printers (D82) carry over ([[MYLA-167]])
- [ ] **The gates:** which test suites run the LLVM backend (parity corpus, stress, concurrency), and whether CI installs LLVM
