---
id: MYLA-284
title: "Big cells in the allocator: a list on wasm32 stops at 2^26 elements"
type: bug
status: todo
priority: medium
labels: [runtime, allocator, wasm]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). A cell above 4 KiB is rounded to the next power of two ([[lib/std/rt.my]], `alloc` size classes), so a list of 2^k elements takes 2^(k+4) bytes, twice its payload, and a freed big cell is never reused by a bigger class; `unmap_memory` is a no-op on wasm32 and native arenas never give memory back. On wasm32 a push loop stops at 67,108,864 elements with `runtime error: out of memory` while the x86-64 build goes on to 300 M; natively the cost is virtual memory only (16 workers touching 24 MB each keep 441 MB resident for good). [[Language/Targets]] notes the wasm32 limit until this is fixed.

- [ ] Size classes above a chunk as multiples (or list capacities of 2^k − 2 so a cell fits a power of two), and reuse of freed big cells across classes
- [ ] Memory returned to the system on the native targets where a whole chunk is free (a decision: D106)
- [ ] The Targets page's Memory row without the limit; a wasm32 test that pushes past 2^27
