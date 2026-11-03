---
id: MYLA-164
title: "Target: macOS"
type: feature
status: backlog
priority: low
labels: [backend, platforms]
---
A target of [[MYLA-62]] after [[MYLA-162]] and the aarch64 backend ([[MYLA-163]]; Intel Macs need the x86-64 one). macOS has no stable system call ABI: the platform layer links libSystem (D117 (2)), and Apple Silicon runs only signed binaries ([[MYLA-160]] settles linking and signing).

- [ ] The platform layer over libSystem (memory, files, processes, threads and parking, thread-local state), on arm64 and x86-64
- [ ] Linking and signing what's needed to run a binary; the parity, stress and concurrency programs pass on a macOS runner
