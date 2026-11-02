---
id: MYLA-230
title: "Sleep, timers, timeouts and suspending I/O on a reactor"
type: feature
status: backlog
priority: low
labels: [concurrency, runtime, io]
---
D107 ([[MYLA-212]]): waits for the runtime off assembly ([[MYLA-162]]). A reactor (epoll on Linux) in the runtime: `sleep`, timers and timeouts on awaits, and I/O in `std.io`/`std.process` that suspends the task instead of blocking the worker.

- [ ] A design after [[MYLA-162]]: the reactor's place in the executor, the platform layer's part, how the interpreters model time
- [ ] `sleep`, timeouts, suspending reads and process waits; tests
