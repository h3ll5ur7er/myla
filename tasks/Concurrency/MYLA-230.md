---
id: MYLA-230
title: "Sleep, timers, timeouts and suspending I/O on a reactor"
type: feature
status: in-progress
priority: low
labels: [concurrency, runtime, io]
---
D107 ([[MYLA-212]]): waits for the runtime off assembly ([[MYLA-162]]). A reactor (epoll on Linux) in the runtime: `sleep`, timers and timeouts on awaits, and I/O in `std.io`/`std.process` that suspends the task instead of blocking the worker.

- [x] A design after [[MYLA-162]]: the reactor's place in the executor, the platform layer's part, how the interpreters model time — D124 ([[MYLA-258]])
- [ ] The clock and `sleep`: `std.time` (`now_ms`, `now_ns`), `task.sleep`, the timer heap and the poller with its event descriptor only; `exec_stuck` with timers; the interpreter's sleeping tasks (real time, `MYLA_TIME=virtual`); tests in both
- [ ] `task.timeout` and cancellation waking reactor waits
- [ ] Suspending reads on pipes and standard input
- [ ] `std.process.run` suspending, on pidfds
