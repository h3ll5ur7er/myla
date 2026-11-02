---
id: MYLA-164
title: "Target: macOS"
type: feature
status: backlog
priority: low
labels: [llvm, platforms]
---
A target of [[MYLA-62]] after [[MYLA-161]] and [[MYLA-162]]. macOS has no stable system call ABI: the platform layer links libSystem, as the LLVM decision ([[MYLA-160]]) decides for D2.

- [ ] The platform layer over libSystem (memory, files, processes, threads and parking, thread-local state), on arm64 and x86-64
- [ ] Linking and signing what's needed to run a binary; the parity, stress and concurrency programs pass on a macOS runner
