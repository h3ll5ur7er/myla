---
id: MYLA-301
title: Litmus programs for the runtime's lock-free protocols on arm64 hardware
type: improvement
status: backlog
priority: medium
labels: [concurrency, memory-ordering, tests]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). [[MYLA-267]] placed acquire and release loads and stores on paper and runs the 26 stress programs on the arm64 runner; the reactor's protocols (`timer_add`, `cancel_locked`, `wait_fds`, `poll_events`) have run only under qemu, which can't reorder, and the stress programs exercise the protocols by accident. The review also found `exec_idle`'s plain read of `__exec_seq` before the glance (made an acquire load with the review).

- [ ] A small set of runtime-level litmus programs (`wait_task` result visibility, park/push, cancel/sleep, timer add/fire, watch add/take) run 1,000 times each on the arm64 job
- [ ] The Native-backend "Parking" row says what the protocol guarantees
