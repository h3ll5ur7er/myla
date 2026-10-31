---
id: MYLA-165
title: "Target: Windows"
type: feature
status: backlog
priority: low
labels: [llvm, platforms]
---
A target of [[MYLA-62]] after [[MYLA-161]] and [[MYLA-162]]: Windows x64, with its own calling convention (the backend's business, [[Architecture/IR]]) and its system DLLs as the platform layer (D98, [[MYLA-160]]).

- [ ] The platform layer over the Windows API (memory, files and paths, processes, threads and waiting, thread-local state, console output in UTF-8)
- [ ] `myla build --target x86_64-windows`; the parity, stress and concurrency programs pass on a Windows runner
