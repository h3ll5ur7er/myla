---
id: MYLA-172
title: Tasked programs reserve 128 GiB of address space; worker stacks have no guard page
type: improvement
status: backlog
priority: low
labels: [concurrency, runtime]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Two runtime limits found by the concurrency review:

- `__heap_init` reserves 32 arenas of 4 GiB (`MAP_NORESERVE`) for any program with a task, whatever `MYLA_THREADS` says: under `ulimit -v 8000000` every tasked program dies with `runtime error: out of memory` while plain programs run. Size the reservation by the number of workers, or grow arenas lazily.
- `__start_workers` maps 8 MiB stacks with no `PROT_NONE` page below them, so an overflow on a worker corrupts the mapping below (another worker's stack, or the heap region) instead of faulting.

- [ ] Reserve per worker, or lazily
- [ ] A guard page under every worker stack (and the main stack's own guard reported as `runtime error: stack overflow`, with [[MYLA-182]])
- [ ] Both documented on [[Architecture/Native-backend]]

Waits for the decision in [[MYLA-206]].
