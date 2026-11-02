---
id: MYLA-207
title: "Decision: scheduling order on one worker (FIFO for parity, or depth-first)"
type: chore
status: review
priority: medium
labels: [decision, concurrency, runtime]
---
From the October 2026 review ([[Project/Review-2026-10]], §11.6 and part of §13.5). With one worker the native runtime runs tasks FIFO, so that its order matches the self-hosted interpreter's. FIFO expands task trees breadth-first: `task.all` over 1.1 M functions takes 20.7 s and 3.3 GB at one worker against 1.7 s and 631 MB at four. Parity of order is bought with an asymptotic memory difference.

## Question

Which order do the implementations promise, and how do tests get determinism?

## Options

- **A. Keep FIFO on one worker** everywhere, as today.
- **B. Depth-first everywhere.** The owner of a queue runs the newest task first (the usual work-stealing policy, thieves take the oldest); both interpreters run a child as soon as it is spawned, so their order still matches native code on one worker. Memory stays proportional to the tree's depth.
- **C. Order unspecified, plus a knob.** No promise about order between tasks; a `MYLA_SCHED` setting (FIFO, LIFO or a seed) makes the stress suite reproducible and lets it explore interleavings (the seeded scheduler of §13.5).

## Recommendation

**B with C's knob**: depth-first in all four runners, the one-worker order still identical across them (the parity tests keep working), the order across several workers documented as unspecified, and a seed for the stress suite.

## Decision

**D110 (2026-11-01): the recommendation.** Implementation: [[MYLA-231]].

- [x] Decided, and recorded on [[Project/Decisions]]
- [x] The implementation tasks created or updated to match
