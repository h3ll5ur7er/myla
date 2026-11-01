---
id: MYLA-172
title: Tasked programs reserve 128 GiB of address space; worker stacks have no guard page
type: improvement
status: review
priority: low
labels: [concurrency, runtime]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Two runtime limits found by the concurrency review:

- `__heap_init` reserves 32 arenas of 4 GiB (`MAP_NORESERVE`) for any program with a task, whatever `MYLA_THREADS` says: under `ulimit -v 8000000` every tasked program dies with `runtime error: out of memory` while plain programs run. Size the reservation by the number of workers, or grow arenas lazily.
- `__start_workers` maps 8 MiB stacks with no `PROT_NONE` page below them, so an overflow on a worker corrupts the mapping below (another worker's stack, or the heap region) instead of faulting.

- [x] Reserve one arena per worker (`MYLA_THREADS`, or the CPUs; at most 32), D106
- [x] A guard page under every worker stack, and an alternate signal stack per worker, so a worker's overflow is reported as `runtime error: stack overflow` like the main stack's ([[MYLA-182]])
- [ ] Both documented on [[Architecture/Native-backend]]

Decided by D106 ([[MYLA-206]]): one arena per worker that can exist and the guard pages now, each worker with an alternate signal stack of its own; lazy arenas move to [[MYLA-162]].

## Evidence

- `_start` reads the environment first, counts the workers (`__workers_count`) and reserves one 4 GiB arena per worker (`MAP_NORESERVE`) instead of 32; `__start_workers` puts a `PROT_NONE` page under each worker's 8 MiB stack (`mprotect`), and each new worker maps a 64 KiB alternate signal stack (`sigaltstack`: a thread made with `CLONE_VM` has none), so the existing `__on_segv` reports a worker's overflow. Only the self-hosted backend has a runtime now ([[MYLA-219]]).
- Tests first, in `tests/burn/test_native_runtime.py`: `test_a_stack_overflow_on_a_worker_is_reported` (four tasks on four workers recursing without end; three runs) printed nothing and died by SIGSEGV (exit -11) before, and prints `runtime error: stack overflow` with exit 1 after; `test_a_tasked_program_reserves_an_arena_per_worker` (one worker under `ulimit -v 6000000`) died with `runtime error: out of memory` before and prints `1` after.
- Lazy arena growth moves to [[MYLA-162]] (D106).

