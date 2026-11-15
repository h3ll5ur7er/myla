---
id: MYLA-703
title: "Windows step 4: memory, threads, thread-local state and stack overflow"
type: feature
status: todo
priority: high
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). D211, D216: `VirtualAlloc` for the heap's chunks, `CreateThread` for the workers, `WaitOnAddress`/`WakeByAddressSingle` for parking, the TEB for each thread's state, a vectored exception handler for a guard-page fault (`runtime error: stack overflow`, status 1).

- [ ] The runtime's heap, workers and parking on the Windows API
- [ ] Stack overflow reported as on Linux, main thread and workers
- [ ] The concurrency and stress programs pass under Wine

## What MYLA-702 left for this step

- The heap's chunks come from `VirtualAlloc` already, and go back through `VirtualFree` (`unmap_memory`): a whole mapping is released, part of one only decommitted, so the ends `std.rt.map_aligned` trims stay reserved addresses (with tasks). An aligned mapping of the platform's own (reserve, then commit the aligned part) would release them.
- Tasks run on one worker: its state block is the first of `__tls_blocks`, addressed next to `%rip` on Windows (`CodeGen.tv`, `rt_var_at`, `Intrinsic.RtAddr` in `ir_x86.my`), `__start_workers` isn't emitted and `_start` sets `__exec_workers` to 1. Workers need each thread's block reached through the TEB (`%gs`: a TLS slot from `TlsAlloc`, or `ArbitraryUserPointer`), not `%fs`, which Wine's own C library holds.
- std.platform's words `__win_io` (a read's or a write's count) and `__win_memory_info` (`VirtualQuery`'s answer) are the process's, which one worker allows: they become each worker's (thread-local) with the workers.
- No stack-overflow report yet; the main stack is reserved by the linker (`/stack:125829120`). A frame larger than a page needs a probe on Windows ([[MYLA-717]]).
