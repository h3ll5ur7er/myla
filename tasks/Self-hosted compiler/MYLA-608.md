---
id: MYLA-608
title: "A third of a hello world's check is page faults: huge pages for the heap's chunks?"
type: improvement
status: review
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

- [x] Decide, build it and measure the check again — option 2 built (a proposal: see below); a hello world's check under 5 ms, its faults 1,130 → 112

## What changed (option 2, a proposal)

- **std.rt** ([[lib/std/rt.my]]): `heap_huge_pages()`, the opt-in. It sets the runtime variable `__heap_huge`, which `alloc_mapped` and `alloc_tasks_mapped` read when they map a chunk, advising it (`MADV_HUGEPAGE`) when set; and it advises the rest of the calling worker's arena from its next 2 MiB boundary and moves the arena's pointer there. The skip matters: by `main` the first chunk already holds the arguments, and a 2 MiB part with a page touched faults 4 KB at a time (the "past each chunk's first 2 MiB" row above: 582 faults); the bytes skipped are address space only, never touched.
- **std.platform**: `advise_huge_pages(p, n)` (`madvise`, 28 on x86-64, 233 on aarch64) and `HUGE_PAGES` (true there, false on wasm32, whose function does nothing and whose `heap_huge_pages` returns at once).
- **The compiler** ([[selfhost/codegen.my]]): the runtime variable `__heap_huge` in every target's data, its own commit and a `Stage:` seed commit before std.rt reads it (D156).
- **The toolchain** calls it: `myla check` and `myla build` ([[selfhost/main.my]], once the command is known), `gen_main` (the bootstrap's stages) and the language server ([[tools/lsp/main.my]]). Not `myla run`, `test` or `repl`: the integration of round 6's follow-up found that a program the interpreter runs pays for them (2026-11-13, `2475f79`): 6,000 extends of 500 bytes took 0.22 to 0.26 s with huge pages against 0.30 to 0.39 s without, but about one run in eight took 0.55 to 1.07 s, failing `test_selfhost_interp`'s `test_lines_and_extended_bytes_take_no_step_a_byte` (about 106 huge-page faults a run, 2 MiB zeroed each, where the program reads 3 MB). A check's heap is a few MB; an interpreted program's is the program's. A program `myla build` builds never calls it, so its chunks are mapped as before; the only thing it carries is the test of `__heap_huge` when it maps a chunk (96 bytes of code).
- **Docs**: [[Architecture/Native-backend]] (the heap), [[Language/Standard-library/Rt]].

### The decision (proposed)

The toolchain opts in with a call of std.rt's at its start, rather than:
1. huge pages for every program with tasks (option 1): every task program pays 0.2 ms at its start and 2 MiB a worker, measured above;
2. an environment variable (`MYLA_HUGE_PAGES=1`): the toolchain would need it set by whoever runs it, so the check wouldn't gain by default;
3. a flag of `myla build`: the same opt-in, but for every program and through the compiler (a new variable's initial value in the data); nothing needs it yet, and a program can call `heap_huge_pages` itself;
4. fewer bytes allocated by the check (option 3): still worth doing, a few hundred KB each, not the 2 ms.

A cost the opt-in takes on: with the kernel's `defrag` on `madvise` (the usual), a fault in an advised region may compact memory to find a huge page when none is free, so under fragmentation a fault can take longer; it falls back to 4 KB pages when compaction fails.

## Evidence

- **Test first**: `tests/burn/test_huge_pages.py` (new; skipped where transparent huge pages aren't on `madvise`). `test_a_check_takes_few_faults` (`myla check` of a hello world, `MYLA_THREADS=1`, fewer than 400 minor faults): with the compiler before, 1,130 faults; after, 112. `test_the_opt_in_maps_the_heap_in_huge_pages`: a program allocating 12 MB of small cells, built by `myla build`, with and without tasks: 5,212 faults without the call (as before: it pays nothing), 25 with `heap_huge_pages()`. Before, it couldn't build (no `heap_huge_pages`).
- **Callgrind** (`MYLA_THREADS=1`, `build/myla check` of `fun main() { print("hello") }`, embedded library): before 20,701,695 instructions, after 20,701,739 (+44: the call and its test).
- **CPU time** (the two binaries alternating, both on the same rounds; the machine shared with other lanes, so only the comparison holds):

| measure | before | after |
| --- | --- | --- |
| 200 runs from a shell loop, as [[MYLA-552]] measured (the shell's share included), `MYLA_THREADS=1`, four rounds | 5.05, 5.72, 5.09, 5.24 ms | 4.16, 3.81, 4.13, 4.45 ms |
| the same, the default threads (4 workers), two rounds | 5.83, 5.36 ms | 4.54, 4.49 ms |
| 300 runs spawned directly (no shell), `MYLA_THREADS=1`, median per run, three rounds | 4.52, 4.71, 4.51 ms | 3.76, 3.75, 3.54 ms |
| minor faults per run (shell loop; spawned directly) | 1,199; 1,132 | 179; 113 |
| system time per run (spawned directly) | 1.20, 0.97, 1.06 ms | 0.58, 0.45, 0.41 ms |

  So **under 5 ms**, with the process's start from the shell included, in every round; before it was over 5 in every round.
- **Bigger runs** (`MYLA_THREADS=1`, medians of 5): `myla check selfhost/main.my` 737 → 669 ms of CPU, 51,436 → 5,794 faults, peak memory 192 → 197 MB; `myla build selfhost/check_main.my` (default threads, 3 runs) 904 → 888 ms, 33,652 → 5,576 faults, 115 → 124 MB.
- **Programs `myla build` builds are unchanged** (1,000 runs a round, two rounds, built by the compiler before and after): a task program that does nothing (`async let a = one()`) 0.71, 0.52 ms before and 0.72, 0.49 after, 19 faults each; a hello world 0.15, 0.12 and 0.12, 0.12 ms, 9 faults each.
- **Other targets**: the 12 MB program built for aarch64 runs under qemu with and without the call, and for wasm32 under node (the call does nothing there); `myla` built for aarch64 checks a hello world and runs a task program under qemu.
- **The bootstrap**: byte-identical fixed point (26,387,289 bytes) from the staged seed.
