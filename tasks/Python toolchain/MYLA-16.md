---
id: MYLA-16
title: Native allocator scans one free list linearly
type: improvement
status: todo
priority: high
labels: [native-backend, performance, bootstrap]
---
`__alloc` searches a single exact-fit free list from the head on every allocation ([[src/myla/compiler/codegen_x86.py#L744-L785]]). With many cells of many sizes this is O(free cells) per allocation, and it is why bootstrap stage 2 (the self-hosted compiler built by the Python backend) takes about 4 minutes while stage 3 takes 2 seconds ([[Development/Bootstrap]]).

**Measured (2026-10-25):** with `__free` turned into a plain `ret` (no reuse at all, arena raised to 2 GiB), stage 2 takes **2.5 s instead of about 4 min** and produces a byte-identical `stage2.s`. The time is spent entirely in the free-list scan. Together with [[MYLA-60]], the whole bootstrap goes from about 5 minutes to about 10 seconds.

Map `remove` is O(capacity) as well: it rebuilds the table instead of leaving tombstones ([[src/myla/compiler/codegen_x86.py#L3043-L3116]]).

## Done when

- [ ] Size-class free lists (for example per 8-byte class up to a few KiB, one list for larger cells), as the self-hosted runtime does
- [ ] Stage 2 time measured before and after on [[Development/Bootstrap]]
- [ ] Arena-reclaim stress tests still pass
- [ ] Optional: tombstone deletion for maps (state 2 is already reserved)
