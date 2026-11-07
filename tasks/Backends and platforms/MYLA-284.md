---
id: MYLA-284
title: "Big cells in the allocator: a list on wasm32 stops at 2^26 elements"
type: bug
status: done
priority: medium
labels: [runtime, allocator, wasm]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). A cell above 4 KiB is rounded to the next power of two ([[lib/std/rt.my]], `alloc` size classes), so a list of 2^k elements takes 2^(k+4) bytes, twice its payload, and a freed big cell is never reused by a bigger class; `unmap_memory` is a no-op on wasm32 and native arenas never give memory back. On wasm32 a push loop stops at 67,108,864 elements with `runtime error: out of memory` while the x86-64 build goes on to 300 M; natively the cost is virtual memory only (16 workers touching 24 MB each keep 441 MB resident for good). [[Language/Targets]] notes the wasm32 limit until this is fixed.

- [x] Size classes above a chunk as multiples (or list capacities of 2^k − 2 so a cell fits a power of two), and reuse of freed big cells across classes
- [x] Memory returned to the system on the native targets where a whole chunk is free (a decision: D106)
- [x] The Targets page's Memory row without the limit; a wasm32 test that pushes past 2^27

## Done (2026-11-07)

- D157. A big cell, one that doesn't fit in a 16 MiB chunk, is a mapping of its own of exactly the 64 KiB pages it needs (`alloc_big`), not the next power of two; `free` gives it back to the system on the native targets (`free_big`, `munmap`), from whichever worker frees it with tasks. On wasm32, which can't give memory back (`os.RETURNS_MEMORY`), a freed big cell goes on `__big_free` for a later big one it is large enough for, and a big list or builder that ends where the memory does grows where it is (`grew_in_place`): no copy and no second cell beside the first. List and builder growth take the whole cell they get as capacity, so a power-of-two class holds no slack.
- The runtime variable `__big_free` came in a commit of its own with the seeds, as the seed that builds the standard library has to declare it first (D156 allows it mid-branch).
- Tests: `test_wasm.test_a_list_past_2_27_elements` (150 million `int64`s; `out of memory` at 2^26 before); `test_native_runtime.test_a_freed_big_list_gives_its_memory_back`, with and without tasks (VmRSS under 100 MB after a 40-million-element list is dropped; it stayed above 300 MB before).
- Measured natively, a list of 150 million `int64`s: peak resident memory 3,192 → 2,063 MB, 2.32 → 1.92 s; on wasm32 it runs in 1.5 s.

