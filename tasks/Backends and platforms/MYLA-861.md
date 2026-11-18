---
id: MYLA-861
title: "Windows: a program of many workers commits 16 MiB of heap for each worker that allocates"
type: bug
status: review
priority: medium
labels: [platforms, windows, memory]
---
Found by [[MYLA-798]] (H12). Windows counts committed memory against the system's limit (RAM and page file), where Linux overcommits: std.platform's `map_memory` ([[lib/std/platform_windows.my]]) reserves and commits at once (`VirtualAlloc` with MEM_COMMIT | MEM_RESERVE), and std.rt's heap ([[lib/std/rt.my]], `alloc_mapped`, `map_aligned`) maps a 16 MiB chunk for each worker's arena the first time that worker allocates, with tasks 32 MiB of it for a moment (`map_aligned` maps a chunk more and gives the ends back). MYLA-798 made the workers' rings of ready frames (8 MiB each) committed as they are touched; the arenas are what is left.

Measured under Wine 9.0 (2026-11-17, MYLA-798's branch): `test_windows.HELPER sleep 3000` with `MYLA_THREADS=16`, a program that does nothing but sleep in one task, had between 4 and 11 mappings `rw-p` of exactly 16 MiB in `/proc/<pid>/maps` across two runs, so 64 to 176 MiB of heap committed. On a 4-CPU runner with 16 GB, 200 such children at once (`process/many-children`) would be some tens of GB.

To reproduce: build `HELPER` for `x86_64-windows`, run it under Wine with `MYLA_THREADS=16` and the arguments `sleep 3000`, and count the 16 MiB `rw-p` mappings of its process. CI's `windows` job (`process/a-child-s-commit`, MYLA-798's rates step) gives the same child's peak commit charge on Windows itself.

- [x] Find why workers that run nothing of the program allocate (the executor's own lists?), and stop it where it isn't needed
- [x] Commit an arena as the bump pointer reaches it (a platform function that commits a range, called by std.rt's allocator past the committed end) rather than at the map: the kernel never faults a reserved page in for a system call that writes into it (`ReadFile` into a fresh buffer fails with ERROR_NOACCESS), so committing on an access violation (what the rings do) doesn't do for the heap
- [ ] A measurement on CI's runner before and after (only the `windows` job: Wine's is below) (`process/a-child-s-commit`'s line in the rates step)

## Evidence

**Why idle workers allocate:** the clock. gdb on HELPER `sleep 500` natively on 16 workers (`break std$rt$alloc_tasks_mapped`): the main thread's first chunk, then every worker thread's from `timers_fire` (or `exec_poll`) → `std.platform.clock_ns` → `__alloc(16)`: every worker reads the clock while a timer waits (`exec_run`'s turn), and Windows' `clock_ns` took its two words from the heap too. Natively 4 to 14 chunks of 16 MiB, 4 KB of each resident. Windows' `clock_ns` now uses the thread's own `__win_memory_info` block (as `unmap_memory` does). The polling worker still allocates (`poll_events`' list, `poller_wait`'s word and `win_call`'s lists): a step of the arena now, not a chunk.

**The arena committed as it is used:** `std.platform` has `HEAP_COMMIT` (Windows 256 KiB, elsewhere 0), `reserve_memory` (Windows `MEM_RESERVE`; elsewhere `map_memory`) and `commit_memory` (`MEM_COMMIT`; elsewhere nothing). Where `HEAP_COMMIT` is set, std.rt reserves a chunk aligned to its size and commits its first step (`chunk_reserved`, before giving back the reservation's ends, as a mapping with nothing committed would be released whole), and `__heap_end` is the end of what is committed: the bump's fast path is unchanged, and a cell past it commits the next steps up to the chunk's end (`arena_committed`), with tasks and without. Committing on a fault, as the rings do, isn't needed: the memory is committed before any cell in it is handed out.

**Measured under Wine 9.0** (2026-11-18; `HELPER sleep 3000`, `MYLA_THREADS=16`, `/proc/<pid>/maps` 1.5 s in, 5 runs each): BASE 8 to 13 mappings `rw-p` of 16 MiB (128 to 208 MiB of heap committed), 403 to 487 MB `rw-p` anonymous in all; after, none, and 273 to 276 MB in all (the rest is Wine's own and the threads' stacks). `test_windows.PlatformFollowUps.test_the_heap_is_committed_as_it_is_used` (no 16 MiB `rw-p` mapping) passes; at BASE it would see 8 to 13. Linux, aarch64 and wasm32 are unchanged (`HEAP_COMMIT` 0). CI's `process/a-child-s-commit` line in the `windows` job's rates step gives Windows' own figure; only that job can.

**Suites** (2026-11-18, this branch): `scripts/test.sh` 1,859 tests OK; `scripts/test-target.py` x86_64-windows 39 of 39 suites, aarch64-linux 38 of 39 then 39 (test_children_run_in_parallel, [[MYLA-745]]), wasm32-wasi 39 of 39; `tests.burn.test_windows` and `test_windows_runner` 73 tests OK under Wine; `scripts/windows-runner.py run --wine --runs 3`: 153 passed, 0 failed, 17 skipped of 170 cases (round 7's integration: 152 of 170, t15 failing); the bootstrap's fixed point, `scripts/check-seed.sh` and its Windows run.

## Proposals

- Built: three names in every platform module, `HEAP_COMMIT` (the step, 0 where mapped memory is usable), `reserve_memory` and `commit_memory`, and a step of 256 KiB (64 calls of `VirtualAlloc` for a chunk at most). Alternatives: (a) Windows' `map_memory` reserving only, with std.rt committing everything it maps (big cells, rings): every caller would have to commit; (b) a smaller step (64 KiB, the allocation granularity): less committed by an idle worker, four times the calls; (c) commit on a fault, as the rings: fails for system calls writing into the heap.
