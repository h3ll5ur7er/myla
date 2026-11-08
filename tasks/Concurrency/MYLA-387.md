---
id: MYLA-387
title: "A runtime primitive to park a task until it is woken"
type: feature
status: backlog
priority: medium
labels: [runtime, concurrency, primitives]
---
Found by the channels lane ([[MYLA-351]]). No primitive parks a task until a condition holds, so a waiting `send`, `recv` or `task.first` looks again: 32 turns, then sleeps of 1, 2 and 4 ms. That costs about 240 ms of CPU for eight tasks idle 2 s on four workers, wakes 1–3 ms late, and caps a channel at about 600,000 messages a second on four workers (3.1 M on one).

- [ ] A park and a wake primitive (a wait queue an actor's method can hold, or a "notify" handle), in `std.rt`'s executor and the interpreter's scheduler, natively on every target; cancellation (D96) ends a park
- [ ] `std.task`'s channels, pool and `first` on it, measured against the polling version
