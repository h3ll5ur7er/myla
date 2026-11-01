---
id: MYLA-231
title: "Depth-first scheduling in every runner; MYLA_SCHED for the stress suite"
type: improvement
status: todo
priority: medium
labels: [concurrency, runtime]
---
D110 ([[MYLA-207]]): the owner of a queue runs its newest task first, thieves take the oldest; the interpreters run a spawned child at once, so the one-worker order stays identical across runners. Today one worker runs FIFO: `task.all` over 1.1 M functions takes 20.7 s and 3.3 GB at one worker against 1.7 s and 631 MB at four.

- [ ] The native executor's local queue LIFO for its owner, FIFO for thieves (both backends, until [[MYLA-219]])
- [ ] The interpreters run a child as soon as it is spawned; the parity programs agree on one worker
- [ ] `MYLA_SCHED=fifo|lifo|seed:N`, used by the stress harness to explore interleavings reproducibly
- [ ] The memory of the review's `task.all` program measured before and after; [[Architecture/Native-backend]] and [[Language/Concurrency]] (order across workers unspecified)
