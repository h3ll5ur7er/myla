---
id: MYLA-608
title: "A third of a hello world's check is page faults: huge pages for the heap's chunks?"
type: improvement
status: todo
priority: medium
labels: [runtime, performance, checker, round-6]
---
Found by round 6's check-time lane ([[MYLA-552]], the last box of [[MYLA-359]]). A hello world's `myla check` (`fun main() { print("hello") }`, `MYLA_THREADS=1`) runs 20.7 M instructions, but a third of its time is the kernel's: it touches 4.1 MB of fresh heap (2.3 MB while loading, 1.8 MB while checking; `/proc/<pid>/smaps` at `build_checker_lazy` and at the exit), one minor page fault per 4 KB page, 1,109 faults in all, about 2.1 ms of system time of about 6.3 ms of CPU per run. Without it the check would be under 5 ms.

The runtime maps the heap in 16 MiB chunks aligned to 16 MiB (`map_aligned` in `lib/std/rt.my`, with tasks), which suits transparent huge pages, but asks for none, and the kernel here gives them only on `madvise` (`/sys/kernel/mm/transparent_hugepage/enabled` is `[madvise]`, as on most distributions).

Measured on the shared container (CPU time of 200 runs a round, the binaries alternating, two rounds, `MYLA_THREADS=1`; the per-run figures include about 1 ms of starting the process from the shell):

| `build/myla` built with | minor faults | `check` of a hello world | a task program that does nothing (`async let a = one()`) |
| --- | --- | --- | --- |
| the runtime as it is | 1,109 | 6.30, 6.00 ms | 0.40, 0.38, 0.41 ms |
| `madvise(chunk, 16 MiB, MADV_HUGEPAGE)` in `map_aligned` | 90 | 5.30, 5.25 ms | 0.60, 0.60, 0.63 ms |
| the same past each chunk's first 2 MiB | 582 | 6.00, 5.85 ms | |

A program without tasks maps its chunks with `map_memory` and is unchanged by either. So huge pages take a millisecond off every check of the toolchain (and more off bigger ones), at 0.2 ms (zeroing a 2 MiB page) and 2 MiB of resident memory more for each worker of every program with tasks that allocates anything.

Options:

1. `MADV_HUGEPAGE` on every chunk with tasks, as measured: the check under 5 ms; every task program pays 0.2 ms and 2 MiB a worker.
2. An opt-in the toolchain makes at its start (a function of std.rt or std.platform that marks the chunks from then on, and the current one), so only the compiler, the language server and `myla` pay for it and gain.
3. Fewer bytes allocated by the check: the loader's renaming copies every declaration of the seven implicit modules, the checker copies each method's signature into two tables (`add_function`, `add_method`); worth doing anyway, but a few hundred KB each.

Recommendation: 2, as it keeps a small program's start as it is. It needs the runtime lane: a new runtime function, which the seed must carry before the compiler calls it (D156's staging).

- [ ] Decide, build it and measure the check again
