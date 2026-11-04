---
id: MYLA-165
title: "Target: Windows"
type: feature
status: backlog
priority: low
labels: [backend, platforms]
---
A target of [[MYLA-62]] after [[MYLA-162]]: Windows x64 through the x86-64 backend, with Windows' own C calling convention (the backend's business, [[Architecture/IR]]) and its system DLLs as the platform layer (D117 (2)); PE/COFF files and linking as [[MYLA-160]] settles.

- [ ] The platform layer over the Windows API (memory, files and paths, processes, threads and waiting, thread-local state, console output in UTF-8)
- [ ] `myla build --target x86_64-windows`; the parity, stress and concurrency programs pass on a Windows runner

## What the first two targets say about this one (2026-11-04, [[Project/Reflection-2026-11]])

- **The calling convention:** Win64 passes four arguments in registers, with 32 bytes of shadow space the caller reserves, and keeps `rsi`/`rdi` callee-saved. Myla's internal convention on x86-64 is System V's; whether Windows keeps it inside Myla code and uses Win64 only at the API boundary is [[MYLA-272]]'s decision. The checker's `become` limit (six words) is System V's count, not Win64's four ([[MYLA-266]]).
- **Objects:** PE/COFF, which the GAS/ELF text doesn't model ([[MYLA-269]]).
- **The poller:** IOCP in place of epoll (D124), through the platform interface in Myla's terms ([[MYLA-265]]).
- **Stack overflow:** guard pages and structured exception handling instead of SIGSEGV on an alternate stack.
- **Thread-local state:** the TEB (`gs:`) instead of `fs:`.
- **Processes:** `CreateProcess` with a command line, not fork/exec; executables found through `PATHEXT` ([[MYLA-190]]).
- **The driver:** it runs the assembler and linker through `/usr/bin/env`, which doesn't exist on Windows ([[MYLA-262]]).

- [ ] [[MYLA-262]], [[MYLA-265]] and [[MYLA-269]] (or their parts this target needs) before the port
