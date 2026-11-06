---
id: MYLA-160
title: "Backends: de-risking D117"
type: chore
status: done
priority: medium
labels: [backend, platforms, design]
---
First step of [[MYLA-62]]. D117 (2026-11-02) chose Myla's own backends from the IR and the runtime in Myla over LLVM. Before the first new backend, the questions that could make that choice expensive are answered with measurements and small prototypes, and recorded on [[Project/Decisions]] (and on [[Architecture/IR]] where they change "Stability"). This replaces the LLVM decision round this task was until then.

- [x] **The gap to C:** benchmarks of Myla native against C at `-O0` and `-O2` (gcc, and clang for what LLVM would win back), and where the time goes ([[MYLA-242]]); no factor fixed in advance: the owner weighs the numbers, the bar being that Myla clearly feels faster than Python. Result ([[Development/Benchmarks]]): about 3× C with Myla's semantics on the geometric mean; clang isn't ahead of gcc; every large gap has a cause and a task ([[MYLA-246]] to [[MYLA-252]]), none needing LLVM
- [x] **The runtime's port:** the runtime ([[MYLA-162]]) sized piece by piece (allocator, strings, maps, builders, formatting, traps, executor, threads), what Myla can't yet express for it (raw memory, atomics for actor handles, `deep`, `clone` and the executor's queues, D92, thread-local state), and what that costs the language. Answered on [[MYLA-162]]: about 2,700 lines of hand-written assembly plus 600 lines of per-type templates (which become IR); raw and bulk memory, atomics as primitives of the standard library, system calls, thread-local state and a few control transfers in the platform layer; no language change; Myla's versions of the hot string routines take 1.2–1.3× the assembly's instructions on a bulk-copy primitive
- [x] **The IR's open points:** a pointer kind ("Untyped addresses"), sizes per target, 32-bit wasm ("Lowered per target"), SSA form for the optimisations of D117 (3). Options and recommendations: [[MYLA-254]] (with memory widths, which [[MYLA-247]] needs). Decided: D120 (widths), D121 (a pointer kind), D122 (sizes per target), D123 (SSA where a pass wants it), D126 (wasm32 keeps 8-byte layouts for now, [[MYLA-260]])
- [x] **Calling conventions:** Myla's own convention on each new backend (arguments above the frame base, the callee popping them, [[MYLA-126]]; `become`, D87; suspended frames, D90), and each platform's C convention for the runtime's platform layer and [[MYLA-166]]. Answered by D119 ([[MYLA-250]]): each target's C convention for Myla's own functions too (System V on x86-64, done; AAPCS64, Win64 and wasm's C convention with their backends), the environment a hidden parameter, `become` by `return_call` on wasm and by the checker's stack-word rule natively; floats in vector registers and 16-byte alignment come with the FFI
- [x] **Object files and linking per platform:** the platform's assembler and linker as external tools, or object files written by Myla (ELF, COFF, Mach-O, wasm modules); signing on macOS
- [x] **Debug information per platform:** the hand-written DWARF (D82) on Linux and macOS, CodeView/PDB on Windows, wasm's own
- [x] **The first backend:** wasm (no register allocation; structured control flow rebuilt from the blocks) or aarch64 (closest to x86-64), decided from the answers above. Built: aarch64 on Linux first ([[MYLA-163]]), then wasm32 on WASI ([[MYLA-158]], D125); what they taught: [[Project/Reflection-2026-11]]
- [x] **Modularity:** what of the toolchain each backend and platform brings along, and what goes into packages ([[MYLA-245]]). Handed on: the backends showed what each target brings (a translation of about 1,500 lines, a runtime file of 500–600, a platform module, its tools); how a target is described and chosen is [[MYLA-262]], code per target [[MYLA-245]]
- [x] **The gates:** how the parity, stress and concurrency suites run on a target the CI machine can't execute (an emulator, a wasm runtime)

## Object files, linking, debug information, gates (2026-11-03)

**What the toolchain needs from the platform today** (measured on the self-compile): GNU `as` takes 26% of a build (0.27 s of 1.09 s; `ld` 5 ms). The generated assembly uses 83 mnemonics in about 130 operand forms and 12 directives (`.text`, `.data`, `.bss`, `.section`, `.global`, `.align`, `.balign`, `.byte`, `.long`, `.quad`, `.ascii`, `.skip`), plus the DWARF sections under `-g`: an encoder of our own for that subset is bounded work.

**Per platform**, from what each one allows:
- *Linux* (x86-64, aarch64): static executables making raw system calls, as today. Writing ELF ourselves (an encoder for the subset above, then sections, symbols and relocations inside one file; no linker, as nothing is linked from outside) removes the binutils dependency and a quarter of the build time. Until then, `as` and `ld` stay.
- *macOS:* raw system calls aren't a stable interface and static executables are rejected on arm64; a program links `libSystem` dynamically and an arm64 binary needs at least an ad-hoc code signature, which edits after linking invalidate. So the platform layer there calls `libSystem` through the C convention (D119), and the first macOS port uses the system linker (which signs); a Mach-O writer of our own with the dynamic-library load commands and the signature blob is possible (Zig has one) but comes later.
- *Windows:* system call numbers change between versions; a program imports from `kernel32`/`ntdll`. A PE writer with an import table is simpler than Mach-O and needs no signature: the natural first choice there, or `lld-link`.
- *wasm:* a module is simple to write ourselves from the start; no external tool.

**Debug information:** DWARF as today on Linux and macOS (lldb reads it); on Windows DWARF first (gdb, lldb), CodeView/PDB for the Microsoft debuggers later (the PDB container is the expensive part); on wasm DWARF in custom sections (browser devtools' DWARF support).

**The gates on targets the CI machine can't run:** `qemu-user` for Linux on aarch64 (or GitHub's arm64 runners), a wasm runtime (wasmtime or node) for wasm, macOS and Windows runners for those; the suites already compare native output with the interpreter, which runs anywhere, so only the program runner changes per target.

**The first new backend** (for the owner): either needs the runtime in Myla first ([[MYLA-162]]), or the 2,700 lines of runtime assembly written again for its machine.
- *aarch64, Linux first:* the question D117 is really about, the cost of a second native backend (instruction selection, register allocation, AAPCS64, ELF for a second machine), on a static Linux target with raw system calls like today's; the most useful port (ARM servers, and Apple Silicon after the macOS platform layer).
- *wasm:* no register allocation, structured control flow rebuilt from the blocks (the lowering's control flow is reducible), 32-bit addresses (D122 first), a runtime without system calls (WASI or a host), one thread to begin with; it tests the IR's and the runtime's portability more than the cost of a native backend.

Recommendation: the runtime in Myla first ([[MYLA-162]]), as every new target needs it; then aarch64 on Linux, as it answers D117's question directly; wasm after it.

Sources: [why macOS kills static executables](https://kiwix.lema.org/stackoverflow.com_en_all_2023-11/questions/71723764/why-does-macos-kill-static-executables-created-by-clang), [Haskell-cafe: no static libSystem](https://mailman.haskell.org/archives/list/haskell-cafe@haskell.org/thread/6MLXKHYSJ4ISUY7KKDZLUJLXWALF2HFJ), [lld: ad-hoc signing on arm64](https://llvm.googlesource.com/llvm-project/lld/+/1d8c290e8c13fdc7432f121c1668659980c9c0de%5E%21/), [Zig: Mach-O code signing](https://github.com/ziglang/zig/issues/6971), [Windows system call numbers](https://www.evilsocket.net/2014/02/11/On-Windows-syscall-mechanism-and-syscall-numbers-extraction-methods/), [Wine: applications use the DLLs](https://list.winehq.org/archives/list/wine-devel@list.winehq.org/message/U7EKLAUAVR7ODG3AJN22AUBNH4KJTWEQ).

