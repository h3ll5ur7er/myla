---
id: MYLA-206
title: "Decision: the runtime's address-space reservation and the worker stacks' guard pages"
type: chore
status: todo
priority: low
labels: [decision, concurrency, runtime]
---
From the October 2026 review ([[Project/Review-2026-10]], §11.5, §13.3 and part of §13.5). A program with one `async let` reserves 32 arenas of 4 GiB (`MAP_NORESERVE`), whatever `MYLA_THREADS` says, so under `ulimit -v 8000000` every tasked program dies with "out of memory". Worker stacks (8 MiB) have no guard page. The main stack's overflow is reported since [[MYLA-182]]; the handler runs on an alternate stack that only the main thread has. Implementation task: [[MYLA-172]].

## Question

How much does the runtime reserve, and how are worker stacks protected?

## Options

Reservation:

- **A. Per worker**: one arena per worker that can exist (`MYLA_THREADS`, at most 32). A small change; still 4 GiB per worker.
- **B. Lazily**: reserve an arena when a worker first allocates, in smaller steps (say 64 MiB chunks). Fits any `ulimit -v`; more code in the allocator.
- **C. Smaller fixed arenas** (1 GiB) with a fallback to a shared arena when one fills.

Worker stacks: a `PROT_NONE` page under each, plus a per-thread `sigaltstack` so the existing handler reports `runtime error: stack overflow` on workers too (the alternate stack is per thread). No real alternative to this one.

## Recommendation

**A plus the guard pages now** (both small, both backends); **B when the runtime moves off assembly** ([[MYLA-162]]), where allocator work is cheaper to write.

## Decision

*Open.* The owner's answer goes here and, once given, onto [[Project/Decisions]] as a numbered decision.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match
