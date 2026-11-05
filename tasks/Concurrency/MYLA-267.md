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

- [x] Each protocol's ordering requirement written down (which stores must be visible before which loads), and the IR's atomics specified to meet them ([[MYLA-264]]): [[Architecture/Native-backend]], "Memory ordering"
- [x] The aarch64 sequences checked against those requirements; three gaps found and fixed (below)
- [ ] The stress programs on arm64 hardware (a GitHub arm64 runner), on 1–16 workers, many runs each

## Done (2026-11-05)

- **Two new primitives:** `__load_acq64` and `__store_rel64` in the checker, the lowering and the three backends. aarch64 emits `ldar` and `stlr`, x86-64 plain `movq`, wasm32 plain loads and stores.
- **Unlocks were plain stores (22 sites):** every `__store64(lock, 0)` after a `take_lock`, on the queues, the actor records and the timers, could become visible before the critical section's stores. They are now `give_lock`, a release store; the poller's claim is given back the same way.
- **`task_wait` read the child's `task` word with a plain load,** then read the child's result: now an acquire load.
- **`__task_fail` claimed the failure flag without a barrier** and then looked at what the workers run, a store then a load: now `dmb ish` after the claim, as the exchanges have. `__cas64` got its barrier with [[MYLA-275]].
- **The requirements of every protocol:** a table on [[Architecture/Native-backend]] ("Memory ordering").
- **The stress programs on hardware:** `scripts/stress-native.py` builds each with the machine's `myla` and runs it 20 times on each of 1, 4 and 16 workers; CI's `bootstrap-arm64` job runs it on GitHub's arm64 runner.

Evidence:
- the concurrency stress, time, native runtime, aarch64 (qemu) and scheduling suites pass, 40 tests;
- `stress-native.py` passes here (0 failed runs);
- the fixed point is reached and the seeds updated.

The arm64 hardware run is the CI job's.
