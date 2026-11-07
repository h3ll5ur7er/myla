---
id: MYLA-301
title: Litmus programs for the runtime's lock-free protocols on arm64 hardware
type: improvement
status: review
priority: medium
labels: [concurrency, memory-ordering, tests]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). [[MYLA-267]] placed acquire and release loads and stores on paper and runs the 26 stress programs on the arm64 runner; the reactor's protocols (`timer_add`, `cancel_locked`, `wait_fds`, `poll_events`) have run only under qemu, which can't reorder, and the stress programs exercise the protocols by accident. The review also found `exec_idle`'s plain read of `__exec_seq` before the glance (made an acquire load with the review).

- [x] A small set of runtime-level litmus programs (`wait_task` result visibility, park/push, cancel/sleep, timer add/fire, watch add/take) run 1,000 times each on the arm64 job
- [x] The Native-backend "Parking" row says what the protocol guarantees

## Evidence

- Five programs in `tests/burn/concurrency_stress/` with their expectations in `test_concurrency_stress.EXPECTED`: t23 (1,024 children's heap results read by their awaiters: `wait_task`'s acquire load), t24 (200 sleepers of a minute cancelled as they start: cancel and sleep), t25 (128 tasks arming 20 short timers each from every worker), t26 (128 tasks yielding 50 times each: park and push through the ready queue), t27 (32 child processes at once, their pipes watched by the poller: watch add and take). Each runs in 3 to 40 ms; 200 runs each on 16 workers here gave the expected output every time, and `test_concurrency_stress` (the interpreter, and natively on 1, 4 and 16 workers) passes.
- `bootstrap-arm64` runs them 1,000 times each on 4 and 16 workers (`scripts/stress-native.py --runs 1000 --workers 4,16 --only …`); here 30 runs each on 4 and 16 workers: 0 failed.
- [[Architecture/Native-backend#memory-ordering]]: the Parking row says what the protocol guarantees (a push made while a worker goes to sleep is run without waiting for another: seen in the last glance, or the sleeper woken, or the futex returning at once; at worst a wakeup for nothing) and reads `__exec_seq` with acquire; new rows for the timers and the descriptor watches; each row names its litmus program.
