---
id: MYLA-140
title: A work-stealing executor
type: feature
status: done
priority: medium
labels: [concurrency, runtime, codegen, selfhost, performance]
---
After [[MYLA-137]] (D92): the native runtime's workers share one ring of ready frames under one lock, so programs of many small tasks hardly scale (every push and pop contends for the lock and its cache line). Each worker gets a queue of its own and steals from the others when it runs out.

- [x] A queue per worker, pushes to the running worker's own
- [x] Stealing when a worker's queue is empty; sleeping and waking, and the "every task waits" error, over all the queues
- [x] The same results on 1 to 16 workers; one worker keeps the self-hosted interpreter's order
- [x] Measured against the shared queue

## Design

- **Queues.** A ring per worker (in a region reserved at start, `MAP_NORESERVE`, 8 MiB each), its head, tail and lock word in a record of its own cache line. The running worker pushes onto its own queue's tail and takes its newest frame: depth first, so a task's children run before its siblings', hot in the cache, and a tree of tasks keeps few frames alive. A frame yielding a turn after an awaited call goes to the oldest end (`__exec_yield_push`), behind the others, so a turn still lets them run. One worker keeps first in, first out for every push: the order of the self-hosted interpreter.
- **Stealing.** A worker whose queue is empty takes the oldest frame of the next worker's queue that has one, going round from its own index. In a tree of tasks the oldest frames are the biggest pieces of work.
- **Sleeping and waking.** As before: `__exec_seq` counts pushes, idle workers spin, then sleep on it, a push wakes one when one sleeps. A worker with nothing gives up its idle count before it takes a frame, and only peeks at the queues while it counts as idle, so "every worker idle and nothing queued" stays exact.
- Considered: the lock-free Chase–Lev deque (pushes and pops without a lock for the owner). The owner's lock here is uncontended unless someone steals, so it costs an `xchg` per push and pop; Chase–Lev is the next step if measurements call for it.

## Baseline (the shared queue)

A binary tree of 131,072 small child tasks (`tree`): 286 ms on one worker, 236 ms on two, 244 ms on four. The deep task trees: 16.5, 21.7, 22.3 ms. Eight CPU-bound children: 5.10, 2.59, 1.28 s.

## Evidence

- First version (every worker taking its oldest frame): the tree took 282, 187 and 113 ms on 1, 2 and 4 workers. Taking the newest frame instead expands a tree depth first: 294, 146 and 80 ms (3.7 times as fast on four workers; the shared queue: 286, 246, 244 ms). The deep task trees: 17.0, 17.9, 16.8 ms (shared: 17.9, 22.3, 22.5). Eight CPU-bound children: 5.08, 2.53, 1.31 s (unchanged). `values_cross_deeply`, whose tasks mostly take turns at one actor: 4.8, 8.6, 11.3 ms (shared: 4.6, 9.5, 10.4): with 47 `futex` calls, its cost is its tasks moving between cores at every actor call, not waking.
- The concurrency, held-failure (one worker), deep-task, any-number-of-workers and parallelism tests pass; the stress run (13 programs, 30 times each on 1, 2, 4, 8 and 16 workers) varied nowhere.
- Unit 621, integration 2, burn 796 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,961,762 bytes). The any-number-of-workers test now runs a tree of 4,096 small tasks too.
