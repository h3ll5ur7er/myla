---
id: MYLA-163
title: "Target: Linux on aarch64"
type: feature
status: backlog
priority: low
labels: [llvm, platforms]
---
The first new target of [[MYLA-62]], the closest to what exists (Linux system calls, no libc), after the LLVM backend ([[MYLA-161]]) and the portable runtime ([[MYLA-162]]).

- [ ] The platform layer for Linux on aarch64 (its system call numbers and conventions, thread-local state, atomics)
- [ ] `myla build --target aarch64-linux`; the parity, stress and concurrency programs pass under qemu or on hardware, in CI if practical
