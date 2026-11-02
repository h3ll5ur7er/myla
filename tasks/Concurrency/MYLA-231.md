---
id: MYLA-231
title: "Depth-first scheduling in every runner; MYLA_SCHED for the stress suite"
type: improvement
status: review
priority: medium
labels: [concurrency, runtime]
---
D110 ([[MYLA-207]]): the owner of a queue runs its newest task first, thieves take the oldest; the interpreters run a spawned child at once, so the one-worker order stays identical across runners. Today one worker runs FIFO: `task.all` over 1.1 M functions takes 20.7 s and 3.3 GB at one worker against 1.7 s and 631 MB at four.

- [x] The native executor's local queue LIFO for its owner, FIFO for thieves, on one worker too (the Python backend is gone, [[MYLA-219]])
- [x] The interpreter runs the same order as native code on one worker; the parity programs agree on one worker
- [x] `MYLA_SCHED=fifo|lifo|seed:N`, used by the stress harness to explore interleavings reproducibly
- [x] The memory of the review's `task.all` program measured before and after; [[Architecture/Native-backend]] and [[Language/Concurrency]] (order across workers unspecified)

## Evidence

- **How.** Native code ([[selfhost/codegen.my]], `emit_executor`) already ran the newest frame first on several workers; on one worker it ran the oldest, for the interpreter's sake. Now every worker count runs the newest first. The self-hosted interpreter's ready queue ([[selfhost/interp.my]]) is now a ring with the same three operations as native code: `ready` (newest end), `ready_behind` (a yield goes to the oldest end) and `next_ready`.
- **Mechanism, not D110's wording.** The interpreter doesn't run a child "as soon as it is spawned", as D110 put it. Both runners queue the child and the parent goes on; that is enough for identical orders and for depth-first memory.
- **A divergence found on the way, older than D110.** The order program below showed that interpreter and native code at one worker already disagreed under the old FIFO order. Native code goes on at once after awaiting a child that has ended; the interpreter yielded its turn there. The interpreter now goes on at once too.
- **`MYLA_SCHED`.** Native code reads it in `_start` (`__sched_init`), the interpreter's drivers from `/proc/self/environ` (`sched_from_env`, `sched_in`, `sched_of`).
  - `fifo` takes the oldest and queues a yield at the newest end: exactly the old order, the same bytes before and after.
  - `seed:N` queues each ready task at the newest or the oldest end, by bit 33 of a 64-bit LCG seeded with N; the same generator runs in both runners.
  - The first version picked a random ready task instead, and the stress suite caught it: under `seed:2` it ran a task that had just yielded again before its sibling, so `t15_failure_beside_a_busy_sibling` printed "never". That broke the documented "a turn goes behind the others" (the Starvation row of [[Language/Concurrency]]). The version kept keeps it.
- **A bug found on the way.** `read_to_string` of a file whose size `fstat` reports as 0 (`/proc/self/environ`, a pipe) returned "". `__read_file` now reads such a file into a cell that doubles until EOF; sized files are read as before.
- **Measurements.** The review's program, `task.all` over 1.1 M functions, native:
  - one worker: 20.83 s and 3,277 MB before, 1.92 s and 354 MB after (`MYLA_SCHED=fifo`: 18.3 s, 3,277 MB, the old order);
  - four workers: 1.44 s and 610 MB before, 1.32 s and 617 MB after.
- **Tests.** `tests/burn/test_scheduling.py` (new):
  - The interpreter and native code at one worker print the same order of `tests/burn/data/sched_order.my` (a `task.all` and a tree of `async let`s with awaits of running and ended children) under the default, `lifo`, `fifo`, `seed:1`, `seed:99` and `seed:4242`: five different orders. Before the change the two runners differed even in the old FIFO order.
  - The default runs the last function of a `task.all` first, `fifo` the first.
  - Depth first, a `task.all` of 300,000 functions peaks below a third of `fifo`'s memory.
- **Stress suite.** `test_concurrency_stress.py` now runs every program, in the interpreter and natively on one worker, with `fifo` and seeds 1 to 3 too.
- **Changed expectation.** `held_exit` in `test_selfhost_codegen.py` pinned the FIFO order. Its new output (`exit` before main's third count) is the interpreter's too.
- **Suite and bootstrap.** The burn suite passes (840 tests) and the bootstrap reaches its fixed point with the new seed.

