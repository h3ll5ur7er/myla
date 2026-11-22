---
id: MYLA-928
title: "Every worker maps about 24 MiB of address space as it starts, so a many-CPU machine under an address-space limit runs out before the program allocates"
type: bug
status: backlog
priority: low
labels: [runtime, memory, concurrency]
---
Found by the owner's timed run on a workstation of 24 CPUs (2026-11-19): `test_archive.ArchiveTest.test_decompression_bomb_natively` runs its program under `RLIMIT_AS` of 256 MiB and expects `error: output longer than max_output`; with 24 workers (one per CPU) it got `runtime error: out of memory` before the bomb began. CI's runners have 4 CPUs, so it passed there.

A program starts `workers_count()` workers (`MYLA_THREADS`, else the CPUs it may run on; [[lib/std/rt.my]]), and each maps its stack and a heap chunk as it starts, whether it ever allocates or not. An idle program (`async fun main() { await task.sleep(400) }`, x86-64, 2026-11-19):

| `MYLA_THREADS` | VmSize | VmRSS |
|---|---|---|
| 1 | 25,008 kB | 72 kB |
| 4 | 123,504 kB | 104 kB |
| 16 | 501,104 kB | 244 kB |

At 4 workers `/proc/<pid>/maps` holds one 32 MiB, four 16 MiB (`CHUNK`) and three 8 MiB mappings: about 24 MiB per worker beyond the first. The bomb test passed with `MYLA_THREADS` up to 12 and failed from 16. Resident memory stays small, so only a limit on address space shows it: `ulimit -v`, `RLIMIT_AS`, a container or job object limited by commit (Windows commits what it maps, [[MYLA-717]]).

The test now pins its program to 4 workers (`MYLA_THREADS=4`), as it is about `max_output`, not about workers.

- [ ] A worker's heap chunk mapped on its first allocation, not as it starts (and its stack smaller, or grown as it is used, where the platform allows)
- [ ] Or workers started as tasks need them, up to `workers_count()`
- [ ] A test: an idle program with `MYLA_THREADS=64` under `RLIMIT_AS` of 256 MiB runs
