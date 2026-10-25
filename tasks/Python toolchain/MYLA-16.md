---
id: MYLA-16
title: Native allocator scans one free list linearly
type: improvement
status: backlog
priority: medium
labels: [native-backend, performance, bootstrap]
---
`__alloc` searches a single exact-fit free list from the head on every allocation ([[src/myla/compiler/codegen_x86.py#L744-L785]]). With many cells of many sizes this is O(free cells) per allocation, and it is why bootstrap stage 2 (the self-hosted compiler built by the Python backend) takes about 4 minutes while stage 3 takes 2 seconds ([[Development/Bootstrap]]).

Map `remove` is O(capacity) as well: it rebuilds the table instead of leaving tombstones ([[src/myla/compiler/codegen_x86.py#L3043-L3116]]).

## Done when

- [ ] Size-class free lists (for example per 8-byte class up to a few KiB, one list for larger cells), as the self-hosted runtime does
- [ ] Stage 2 time measured before and after on [[Development/Bootstrap]]
- [ ] Arena-reclaim stress tests still pass
- [ ] Optional: tombstone deletion for maps (state 2 is already reserved)
