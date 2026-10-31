---
id: MYLA-16
title: Native allocator scans one free list linearly
type: improvement
status: done
priority: high
labels: [native-backend, performance, bootstrap]
---
`__alloc` searches a single exact-fit free list from the head on every allocation ([[src/myla/compiler/codegen_x86.py#L744-L785]]). With many cells of many sizes this is O(free cells) per allocation, and it is why bootstrap stage 2 (the self-hosted compiler built by the Python backend) takes about 4 minutes while stage 3 takes 2 seconds ([[Development/Bootstrap]]).

**Measured (2026-10-25):** with `__free` turned into a plain `ret` (no reuse at all, arena raised to 2 GiB), stage 2 takes **2.5 s instead of about 4 min** and produces a byte-identical `stage2.s`. The time is spent entirely in the free-list scan. Together with [[MYLA-60]], the whole bootstrap goes from about 5 minutes to about 10 seconds.

Map `remove` is O(capacity) as well: it rebuilds the table instead of leaving tombstones ([[src/myla/compiler/codegen_x86.py#L3043-L3116]]).

## Done when

- [x] Size-class free lists: one per 8-byte class up to 4 KiB (`_SMALL_CELL_LIMIT`, the self-hosted runtime's limit), larger cells on the old exact-fit list; `__free` still clobbers only `%rax`
- [x] Test first: `test_allocation_does_not_scan_unusable_free_cells` timed out at 5 s before (the linear scan needs about 14 s), passes in about 2 s including the build
- [x] A 300,000-allocation version of that workload: 137 s → 1.4 s
- [x] Stage 2: about 4 min → 1.3 s; full bootstrap 5 min → 7.8 s, fixed point holds, `stage2.s` identical to before; recorded on [[Development/Bootstrap]]
- [x] Arena-reclaim stress tests still pass; the generated assembly differs from before only in `__alloc`, `__free` and `.bss`
- [x] Optional: tombstone deletion for maps (state 2 is already reserved): moved to [[MYLA-151]]
