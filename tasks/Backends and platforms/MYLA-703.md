---
id: MYLA-703
title: "Windows step 4: memory, threads, thread-local state and stack overflow"
type: feature
status: todo
priority: high
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). D210, D215: `VirtualAlloc` for the heap's chunks, `CreateThread` for the workers, `WaitOnAddress`/`WakeByAddressSingle` for parking, the TEB for each thread's state, a vectored exception handler for a guard-page fault (`runtime error: stack overflow`, status 1).

- [ ] The runtime's heap, workers and parking on the Windows API
- [ ] Stack overflow reported as on Linux, main thread and workers
- [ ] The concurrency and stress programs pass under Wine
