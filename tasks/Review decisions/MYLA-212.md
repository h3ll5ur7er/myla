---
id: MYLA-212
title: "Decision: the next concurrency slice, what goes in and in which order"
type: chore
status: todo
priority: low
labels: [decision, concurrency]
---
From the October 2026 review ([[Project/Review-2026-10]], §13.5). Candidates: a `sleep`/`yield` builtin; suspending I/O behind `std.io`/`std.process` (an epoll or io_uring reactor), timers and timeouts; cleanup on failure or cancellation (`defer`, scoped resources, or a `Result`-returning task API); async trait methods; a non-reentrant method kind; D95 extended through `self` methods ([[MYLA-171]]); a seeded scheduler for the stress suite and depth-first scheduling ([[MYLA-207]]); lazy arena growth ([[MYLA-206]]); a move optimisation for values crossing tasks at their last use.

## Question

Which of these form the next slice, and which wait?

## Options

- **A. Small and safe**: [[MYLA-171]] (a known hole in a checker warning), the scheduler decisions of [[MYLA-207]], `yield`, and `defer` (useful beyond concurrency, also for file handles in [[MYLA-211]]).
- **B. A reactor slice**: `sleep`, timers, timeouts and suspending I/O on epoll. The biggest gain for real programs; a large piece of hand-written assembly runtime in two backends today.
- **C. Language slice**: async trait methods and a non-reentrant method kind.
- **D. Nothing now**: concurrency rests until the ergonomics round and the standard library are done.

## Recommendation

**A soon, B after the runtime moves off assembly** ([[MYLA-162]]), where a reactor is far cheaper to write and to port; C when a program needs it. The move optimisation belongs with the IR work (frame layout, [[MYLA-210]]).

## Decision

*Open.* The owner's answer goes here and, once given, onto [[Project/Decisions]] as a numbered decision.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match
