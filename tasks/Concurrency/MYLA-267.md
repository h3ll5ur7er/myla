---
id: MYLA-267
title: "The runtime's memory ordering on weakly ordered CPUs"
type: chore
status: backlog
priority: high
labels: [concurrency, runtime, platforms]
---
Found by [[Project/Reflection-2026-11]]. The executor's lock-free protocols were argued from x86-64's strong ordering, where `lock cmpxchg`, `xchg` and `lock or` are full barriers ([[MYLA-140]], [[MYLA-147]], [[MYLA-150]]):
- a worker publishes the frame it takes, then looks at the flags;
- `__exec_seq` and the parking protocol;
- the actor lock word;
- the remote-free list;
- the failure flag;
- results published to the waiters.

aarch64 is weakly ordered. Its backend uses `ldaxr`/`stlxr` loops plus a `dmb ish` after the exchanges, and passed the stress programs under qemu. But qemu on an x86-64 host doesn't reorder memory, so a missing barrier could not show.

- [ ] Each protocol's ordering requirement written down (which stores must be visible before which loads), and the IR's atomics specified to meet them ([[MYLA-264]])
- [ ] The aarch64 sequences checked against those requirements; the first suspect is the stuck check's plain loads in `exec_idle` ([[MYLA-275]], seen failing once under qemu)
- [ ] The stress programs on arm64 hardware (a GitHub arm64 runner), on 1–16 workers, many runs each
