---
id: MYLA-161
title: "LLVM: user code on x86-64 Linux, linked with the assembly runtime"
type: feature
status: done
priority: medium
labels: [llvm, backend]
---
> [!NOTE]
> **Dropped by D117** (2026-11-02): Myla gets its own backends from the IR instead of LLVM ([[MYLA-62]], [[MYLA-160]]), so user code through LLVM won't be built. Nothing of it was started. In `review` for the owner to close; the text below is the plan as it was.

Second step of [[MYLA-62]], after the decisions ([[MYLA-160]]): an LLVM backend for the IR ([[selfhost/ir.my]]) that emits user code (functions, lambdas, adapters) and the generated helpers (the per-type retain, drop and clone walks, thunks, environment release functions) as LLVM IR, and links them with the existing hand-written x86-64 runtime. Same target, same runtime: the IR-to-LLVM mapping is checked against the parity tests without porting anything else first.

- [ ] Every instruction and terminator of [[Architecture/IR]] in the LLVM backend: slots as `alloca`s (LLVM builds SSA), frame functions' slots in their heap frame, `become` and `suspend` as `musttail` calls, `retain`/`drop`/`cow`/`deep`/`clone` (dropped by D117: no LLVM backend)
- [ ] The calling convention decided in [[MYLA-160]] between LLVM code and the runtime (the executor resuming frame functions, function values) (dropped by D117: no LLVM backend)
- [ ] The native parity programs, the stress tests and the concurrency programs pass with `--backend llvm`; the compiler compiled through LLVM compiles itself to the same output (dropped by D117: no LLVM backend)
- [ ] Measured against the assembly backend: compile time, binary size, run time of the compiler and of the benchmarks of [[MYLA-140]] and [[MYLA-150]] (dropped by D117: no LLVM backend)

LLVM was dropped by D117; closed with the owner's agreement (2026-11-05).
