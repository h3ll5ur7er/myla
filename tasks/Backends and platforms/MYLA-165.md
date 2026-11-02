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
