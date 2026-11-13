# Benchmarks

How far Myla's native code is from C, and where the time goes ([[MYLA-242]]). This is the first input for de-risking D117: Myla gets backends of its own, not LLVM ([[MYLA-160]]).

No factor is fixed in advance: the numbers inform the owner's decision. The bar is that Myla programs clearly *feel* faster than Python, though Python isn't measured.

[TOC]

## Running them

    python3 benchmarks/run.py [name ...] [--runs N] [--no-callgrind] [--json FILE] [--compare FILE]

It needs gcc, and ideally clang and valgrind. Each benchmark is a directory under `benchmarks/`:
- `<name>.my`: the program, written as a user would write it;
- `<name>.c`: idiomatic C;
- `<name>_myla.c`: C with Myla's semantics;
- `bench.json`: `size` for the timing, `profile_size` for callgrind, `test_size` for the test.

`tests/burn/test_benchmarks.py` runs every version at `test_size` and requires the same output, so the set can't drift into measuring wrong programs.

## Method

- **Same algorithm on both sides, written plainly.** No hand-tuned C, single-threaded. The compiler isn't tuned for the benchmarks before they are measured.
- **Five versions of each program:**

  | Version | What the comparison with Myla shows |
  |---|---|
  | Myla, `build/myla build` | |
  | Idiomatic C, gcc `-O2` | The total gap |
  | C with Myla's semantics, gcc `-O2` | What code generation and the runtime cost |
  | The same, clang `-O2` | What LLVM's optimizer would win back on the same semantics |
  | The same, gcc `-O0` | A baseline: an unoptimizing compiler |

- **"C with Myla's semantics"** (`benchmarks/myla_rt.h`) does the work Myla's semantics require, as a good implementation would:
  - a reference count where a value is shared or dropped;
  - a bounds check on every index;
  - a copy before writing to a list someone else also holds (copy-on-write);
  - wrapping `int32` arithmetic (all C is compiled with `-fwrapv`);
  - a trap on division by zero.

  It uses `malloc`, not Myla's allocator.
- **Measured:**
  - wall, user and system time (the median of several runs);
  - page faults, peak memory and binary size;
  - the instructions valgrind's callgrind counts, at a smaller size: exact, so the noisy machine doesn't matter;
  - for the Myla version, the functions those instructions go to. Myla's labels have no symbol type, so `run.py` names valgrind's addresses with `nm`.
- **Time and instructions disagree on purpose.** A microcoded instruction (`rep movsq`), a cache miss or a page fault takes much longer than its count says, so both are needed.

## Results (2026-11-03)

All twelve programs, after [[MYLA-246]], at `9a17dc1`, on the development container (4 cores of an Intel Xeon at 2.3 GHz). Times are the median of 5 runs; instructions are at each program's smaller `profile_size`.

**This is the baseline** for the optimisations that follow, saved as `benchmarks/results/2026-11-03-baseline.json`. `run.py --compare benchmarks/results/2026-11-03-baseline.json` shows each Myla program's change against it. Timings only compare on the same kind of machine; the file records which.

| Benchmark (size) | Myla | C, gcc `-O2` | C + semantics, gcc `-O2` | Same, clang `-O2` | Same, gcc `-O0` | Myla's instructions ÷ C + semantics (gcc) | Myla's peak memory |
|---|---:|---:|---:|---:|---:|---:|---:|
| fib (36) | 98 ms | 20 ms | 20 ms | 40 ms | 98 ms | 1.86× | 14 MB (1.0×) |
| ackermann (11) | 498 ms | 54 ms | 55 ms | 111 ms | 496 ms | 3.34× | 14 MB (1.0×) |
| mandelbrot (3,000) | 903 ms | 231 ms | 225 ms | 235 ms | 517 ms | 4.27× | 14 MB (1.0×) |
| n body (1,000,000) | 1,326 ms | 311 ms | 318 ms | 328 ms | 957 ms | 5.93× | 14 MB (1.0×) |
| sieve (40,000,000) | 1,378 ms | 258 ms | 279 ms | 284 ms | 609 ms | 2.09× | 817 MB (20.6×) |
| fannkuch (10) | 386 ms | 191 ms | 267 ms | 259 ms | 744 ms | 1.38× | 14 MB (1.0×) |
| game of life (1,000) | 861 ms | 230 ms | 297 ms | 314 ms | 1,218 ms | 1.90× | 23 MB (1.6×) |
| quicksort (1,000,000) | 324 ms | 170 ms | 230 ms | 182 ms | 428 ms | 1.69× | 87 MB (5.2×) |
| binary trees (18) | 2,041 ms | 1,029 ms | 1,006 ms | 1,092 ms | 1,573 ms | 1.00× | 80 MB (2.4×) |
| closures (4,000,000) | 806 ms | 281 ms | 248 ms | 325 ms | 528 ms | 2.96× | 124 MB (2.6×) |
| word freq (5,000,000) | 952 ms | 137 ms | 320 ms | 268 ms | 434 ms | 1.37× | 50 MB (1.4×) |
| string build (2,000,000) | 528 ms | 190 ms | 340 ms | 321 ms | 389 ms | 0.39× | 57 MB (1.5×) |

### Summary

- **Myla against C with Myla's semantics at gcc `-O2`:** 1.4× to 9× the time, about **3×** on the geometric mean. The closest are quicksort (1.4×), fannkuch (1.4×) and string building (1.6×); the furthest are Ackermann (9×), fib and the sieve (5×).
- **Against an unoptimizing compiler (gcc `-O0`):** about 1.2× on the geometric mean. Myla is ahead on fannkuch, Game of Life and quicksort, level on fib and Ackermann, behind on floats, the sieve's memory and the string programs.
- **LLVM isn't ahead of gcc on Myla's semantics.** clang `-O2` takes 1.13× gcc `-O2`'s time on the geometric mean: faster on quicksort and word frequency, half as fast on fib and Ackermann. Whatever the gap is, an optimizer of gcc's class closes it, and a better one isn't needed.
- **Against Python** (not measured, as agreed): CPython usually takes tens of times C's time on loops like these. Myla, at 1.4–9×, clearly feels faster.

### Where the gap is, and what closes it

Every large gap has a cause the profiles and the assembly show, and each has a task of its own. None of them needs LLVM.

| Cause | Where it shows | Task |
|---|---|---|
| Small values copied with `rep movsq` | Binary trees 5.9 → 2.0 s, the self-compile about 20 % faster | [[MYLA-246]] (fixed) |
| Float values in general-purpose registers: five instructions and two register-file crossings per operation | mandelbrot 4.3×, n-body 5.9× C's instructions | [[MYLA-249]] |
| 8 bytes per list element | Peak memory: sieve 21×, quicksort 5×, closures 2.6×; page faults (0.4–2.8 s of system time in the sieve) | [[MYLA-247]] |
| Arguments on the stack, moved through memory by tail calls | fib 5×, Ackermann 9× the time | [[MYLA-250]] |
| Checks and widening repeated in loops: list reloaded, copy-on-write and bounds checks per write, `movslq` after each operation | sieve 2.1×, Game of Life 1.9×, fannkuch 1.4× the instructions | [[MYLA-251]] |
| The runtime's string routines (`__str_concat`, `__sb_append_bytes`, `__uint_to_str`) | String building and word frequency: fewer instructions than C, more time | [[MYLA-252]] |
| No square root (n-body takes 16 Newton steps in every version) | n-body: `root` is 45 % of Myla's instructions | [[MYLA-248]] |

The remaining binary-trees gap (2× C's time at C's instruction count) is memory: 2.6× the first-level cache misses, and 80 MB against 34 MB, from a larger enum cell and the allocator's holding.

## Progress: the first optimisation pass (2026-11-03)

One pass through the findings, against the baseline. `benchmarks/results/2026-11-03-after-pass1.json` holds the full results.

| Benchmark | Baseline | After the pass | Speed-up | Against C with Myla's semantics, before | After |
|---|---:|---:|---:|---:|---:|
| fib | 98 ms | 97 ms | 1.02× | 5.02× | 4.68× |
| ackermann | 498 ms | 473 ms | 1.05× | 9.03× | 8.74× |
| mandelbrot | 903 ms | 305 ms | **2.96×** | 4.02× | **1.35×** |
| n-body | 1,326 ms | 212 ms | **6.26×** | 4.17× | 5.35× |
| sieve | 1,378 ms | 1,468 ms | 0.94× (noise) | 4.93× | 5.28× |
| fannkuch | 386 ms | 388 ms | 0.99× | 1.44× | 1.45× |
| game of life | 861 ms | 943 ms | 0.91× (drift) | 2.90× | 3.17× |
| quicksort | 324 ms | 334 ms | 0.97× | 1.41× | 1.32× |
| binary trees | 2,041 ms | 2,115 ms | 0.97× | 2.03× | 2.04× |
| closures | 806 ms | 708 ms | 1.14× | 3.25× | 2.58× |
| word frequency | 952 ms | 617 ms | **1.54×** | 2.97× | 1.83× |
| string building | 528 ms | 327 ms | **1.62×** | 1.55× | **0.92×** |

- **Overall:** 1.37× as fast on the geometric mean; against C with Myla's semantics, 3.06× → 2.57×. String building is now faster than the C version.
- **What did it:**
  - [[MYLA-248]] `std.math`'s `sqrt` (n-body);
  - [[MYLA-249]] floats in `%xmm` registers (mandelbrot, and n-body's arithmetic);
  - [[MYLA-252]] short byte copies without `rep movsb` (the string programs, closures' list copies);
  - [[MYLA-251]] three peepholes (a few percent in loops).

  n-body's C versions switched to `sqrt` as well, so its column against C moved the other way: the C version gained more from the real square root.
- **Timings drift between sessions.** Every program runs fewer instructions than in the baseline (0.7 % to 2.3× fewer). Game of Life's apparent slowdown came from the machine: built by each commit's compiler of the pass, the baseline's included, and timed interleaved, all five versions take 890–910 ms. Compare instruction counts across sessions, or time interleaved; a stored timing alone can be off by ±5 %.
- **Still open:**
  - [[MYLA-247]] packed list elements, the sieve's memory, left for its own round with a plan;
  - [[MYLA-250]] arguments in registers, fib and Ackermann, a design for the owner to decide;
  - the analyses of [[MYLA-251]] (hoisting copy-on-write checks, proving bounds), the sieve, Game of Life, fannkuch.

## Progress: arguments in registers (2026-11-03)

[[MYLA-250]] made Myla's calls System V's (D119): the first six argument words in registers, the rest on the stack, popped by the caller; a function value's environment in `%r10`. A tail call of the function itself became a jump to its entry block. `benchmarks/results/2026-11-03-after-250.json` holds the full results.

Timed interleaved against the same sources built with the stack convention (7 runs each, alternating), and instructions at `profile_size`:

| Benchmark | Stack convention | Registers | Speed-up | Instructions |
|---|---:|---:|---:|---:|
| fib | 97 ms | 88 ms | 1.10× | same |
| ackermann | 476 ms | 495 ms | 0.96× | 10% fewer |
| mandelbrot | 308 ms | 306 ms | 1.01× | same |
| n-body | 221 ms | 217 ms | 1.02× | same |
| sieve | 1,451 ms | 1,507 ms | 0.96× | same |
| fannkuch | 375 ms | 415 ms | 0.90× | same |
| game of life | 900 ms | 900 ms | 1.00× | same |
| quicksort | 344 ms | 345 ms | 1.00× | 2% fewer |
| binary trees | 2,128 ms | 2,113 ms | 1.01× | same |
| closures | 730 ms | 705 ms | 1.04× | 2% more |
| word frequency | 627 ms | 611 ms | 1.03× | same |
| string building | 312 ms | 318 ms | 0.98× | same |

- **Overall: the same time** (1.00× on the geometric mean). The convention is the platform's now, which the FFI and every new backend need (D117, D119), but at this register allocator's level it doesn't make calls cheaper by itself.
- **Why:** a push became a register move, and a load from above the frame a register read: one instruction for one. A parameter that gets no register of its own is now stored into the frame on entry, where it used to be read in place, which is closures' 2% more instructions. Keeping it in the register it came in needs the allocator to know which instruction sequences use `%rcx`, `%rdx`, `%rsi` and `%rdi` as scratch.
- **fannkuch and the sieve** run the same loops instruction for instruction: only their one-time prologue differs (two stores) and their frame cells moved by 16 bytes. Rerun, fannkuch's gap was 3%; shifting the old code by the same 8 bytes didn't slow it. It is placement, within the machine's spread, not code.
- **Ackermann** runs 10% fewer instructions (its tail calls of itself are a loop now) but not faster: `m` has no register (the allocator's threshold for a callee-saved one), so the loop stores and reloads it every iteration. Given `%rbx` by hand, it ran about 6% faster.
- **The self-compile:** within the spread of the stack convention (medians of 0.72–0.75 s either way, over three series of 7 to 11 runs); 0.6% more instructions from the convention, 0.4% more from the compiler's own new work (the checker's rule, the scan for unread parameters).
- **What closes fib's and Ackermann's gap to C** is the optimizer's work, not the convention: gcc `-O2` keeps everything in registers, leaves frames out and turns the recursion partly into loops ([[MYLA-251]]).

## Progress: packed list elements (2026-11-03)

[[MYLA-247]] (D120): a list stores its elements at their natural size, a `bool` in one byte, an `int` in four, where every element took eight bytes. `benchmarks/results/2026-11-03-after-247.json` holds the full results; against the run after [[MYLA-250]]:

| Benchmark | Before | After | Speed-up | Peak memory | Against C with Myla's semantics |
|---|---:|---:|---:|---:|---:|
| sieve | 1,531 ms | 363 ms | **4.21×** | 817 → 102 MB | 1.21× |
| closures | 674 ms | 486 ms | **1.39×** | 124 → 62 MB | 1.65× |
| fannkuch | 407 ms | 347 ms | 1.17× | 14 MB | 1.28× |
| game of life | 924 ms | 874 ms | 1.06× | 23 → 14 MB | 2.97× |
| quicksort | 332 ms | 317 ms | 1.05× | 87 → 75 MB | 1.31× |
| the other seven | | | 0.97–1.09× (spread) | unchanged | |

- **Overall:** against C with Myla's semantics at gcc `-O2`, 3.06× at the baseline, 2.57× after the first pass, 2.51× after MYLA-250, **2.12×** now (geometric means); the same programs run 1.64× as fast as at the baseline.
- **The sieve** was the largest memory gap (21× C's peak); it is 2.6× now, from the capacity's doubling (2²⁶ bytes) and the previous buffer held during the last copy, and 1.21× C's time.
- **The self-compile** (the same compiler source built both ways): 0.95% fewer instructions, the same time, peak memory 135 → 131 MB.
- **Still open:** fib, Ackermann and n-body (4–8× C) are calls and loops the optimizer of D117 (3) would improve ([[MYLA-251]], D123); binary trees' and quicksort's memory (2.4×, 4.4× C's) come from the allocator's holding and copies.

## Progress: map removal (2026-11-07)

[[MYLA-310]] added a thirteenth program, `map_remove`: n keys inserted and all removed, then a working set of 1,000 live keys sliding over 4n keys, with replaced values and keys removed and inserted again, the keys' final order in the result. The C versions keep the insertion order as Python's dict does (entries in order, an index of their positions, compaction). Its baseline, taken before the fix, is `benchmarks/results/2026-11-07-map-remove-before.json`, the run after it `2026-11-07-map-remove-after.json`.

| `map_remove` (32,000) | Before | After | C, gcc `-O2` | C with Myla's semantics |
|---|---:|---:|---:|---:|
| Time | 16,248 ms | 15 ms | 5 ms | 7 ms |
| Instructions (at 4,000) | 4,361 M | 14.9 M | 5.3 M | 5.8 M |

- **Before**, each `remove` rebuilt the whole table to keep the insertion ranks dense, so emptying a map was quadratic: 41 % of the instructions were the rebuild's `map_set_slot` and 29 % its `zero_bytes`.
- **After**, a removal leaves a tombstone and a gap in the ranks; `keys` and `for` skip the gaps, and an insert compacts the table when the slots used since the last compaction reach 3/4 of it. The program is 1,100× as fast, 2.2× C with Myla's semantics.
- **Elsewhere:** word frequency, whose map only grows, runs in the same time natively (603 and 605 ms, the median of 9 interleaved runs; 0.6 % more instructions for the next-rank word) and 3× as fast interpreted (8.3 → 2.8 s at 100,000 words), whose map lookups were linear before.

## Progress (2026-11-09)

All thirteen programs after the standard library waves, D175 (#54) and batches 4 and 5 (#55), at d8a6e9a: `benchmarks/results/2026-11-09.json` holds the full results. This container is a 2.1 GHz Xeon where the baseline's was 2.3 GHz, and its C runs up to 3× slower on some programs (Ackermann's 54 → 160 ms), so the table compares each program's ratio to C measured on the same machine, and the instructions callgrind counts, which don't depend on it. Times are the median of 5 runs.

| Benchmark | Baseline, × C with Myla's semantics | Now, × C with Myla's semantics | Now, × idiomatic C | Myla's instructions, baseline → now |
|---|---:|---:|---:|---:|
| string build | 1.55 | **0.71** | 1.18 | 1.19× fewer |
| fannkuch | 1.44 | 1.15 | 1.48 | 1.43× fewer |
| quicksort | 1.41 | 1.21 | 1.76 | 1.24× fewer |
| mandelbrot | 4.02 | **1.24** | 1.32 | 2.92× fewer |
| sieve | 4.93 | **1.35** | 1.55 | 1.73× fewer |
| binary trees | 2.03 | 1.69 | 1.79 | the same |
| word frequency | 2.97 | 1.78 | 4.32 | 1.05× fewer |
| closures | 3.25 | 2.39 | 1.76 | 1.69× fewer |
| map removal | (added since) | 2.33 | 2.87 | |
| game of life | 2.90 | 2.98 | 3.63 | 1.18× fewer |
| fib | 5.02 | 4.16 | 4.27 | 1.16× fewer |
| n-body | 4.17 | 4.42 | 4.41 | 2.63× fewer |
| Ackermann | 9.03 | 7.08 | 7.16 | 1.56× fewer |

- **Overall:** against C with Myla's semantics at gcc `-O2`, **2.02×** on the geometric mean of the twelve shared programs (3.06× at the baseline), with 1.47× fewer instructions. Against idiomatic C, 2.46× over all thirteen; against gcc `-O0`, 0.74×: faster than an unoptimizing compiler.
- **What closed the gap** was the work of 2026-11-03 to 07 more than anything since: floats in xmm registers and a square root ([[MYLA-248]], [[MYLA-249]]: mandelbrot, n-body), packed list elements ([[MYLA-247]]: the sieve's memory 817 → 80 MB), the loops' checks ([[MYLA-251]]) and the string routines ([[MYLA-252]]: building strings is now faster than the C with Myla's semantics). D175 left plain builds as they were (the same binaries' sizes, instructions within a dozen).
- **Where the gap is:** calls and registers (fib and Ackermann at 4–7× the time, Ackermann at only 2.2× the instructions: the stores and reloads around each call), float code (n-body runs 5.9× gcc's instructions, 88 % of them in `advance`), a small per-cell function that isn't inlined (Game of Life), and memory (binary trees and quicksort at 2–3× C's peak). The owner put the first two aside for now (2026-11-09).

## Progress: maps shrink on remove (2026-11-11)

[[MYLA-429]] makes a removal from a map with fewer keys than an eighth of its capacity compact it (std.rt's `map_shrink`): a map emptied by removals shrinks, and a walk over it costs the keys it has left. 20,000 keys taken oldest-first from a map that once held a million took 94 s and take 3.6 s, as from a map that never held more (2.8 s). The runs before and after are `benchmarks/results/2026-11-11-map-shrink-before.json` and `…-after.json`; instructions by callgrind, which a noisy machine doesn't change.

| Myla's instructions | Before | After | Change |
|---|---:|---:|---:|
| `word_freq` (100,000), its map only grows | 140.64 M | 140.47 M | −0.1 % |
| `map_remove` (4,000) | 15.12 M | 15.78 M | +4.4 % (three runs each: +3 %) |
| the compiler compiling itself | 9,340.08 M | 9,340.37 M | +0.003 % |

- A removal that doesn't shrink runs four instructions more (the capacity loaded, the count shifted, a compare and a branch): `map_remove`'s working set, which never shrinks, 1.68 → 1.76 M instructions in `slide`.
- `map_remove`'s first part empties a map of 4,000 keys, which now compacts it five times on the way (to 2,048 slots, then 512, 128, 32 and 8): about 0.38 M instructions in `map_rehash`, `map_by_rank`, `map_set_slot` and `zero_bytes`, the price of the shrinking, amortised O(1) per removal. Some 0.2 M of the rest is the executor's idle loop, which varies by that much from run to run.
- Times are the same within noise (`word_freq` 901 → 841 ms, `map_remove` 30 → 23 ms, the median of 5).

## Progress: a `for` over a map walks its slots (2026-11-11)

[[MYLA-496]] makes `for k in m` step through the map's slots in the order of insertion (std.rt's `map_walk`, through an order of the slots by rank kept in the cell) instead of making the list of its keys first, and start at the first rank that may still be a key's: a loop that leaves at its first key costs the gaps since the last one. 20,000 keys taken oldest-first by `for k in m { first = k; break }` took 2.6 s natively and 9.7 s interpreted, and take 3 ms and 0.19 s.

| Myla's instructions | Before | After | Change |
|---|---:|---:|---:|
| `word_freq` (100,000) | 140.47 M | 140.58 M | +0.08 % |
| `map_remove` (4,000) | 15.78 M | 15.90 M | +0.7 % |
| the compiler compiling itself | 12,189.6 M | 12,194.9 M | +0.04 % |

- An insert stores its slot's index in the order (4 bytes a slot more, 12.5 % of an `[int: int]` map's 32-byte slot), and a compaction walks the order: `map_remove`'s `map_by_rank` and the `zero_bytes` of its block are gone, `map_set_slot` and `map_rehash` run a little more.

## How the first round went

The first round (fib, the sieve, binary trees) checked the method and needed two additions to `run.py`: user and system time and page faults, and names for valgrind's addresses. Instruction counts alone hid both large gaps of the round: the sieve's page faults, and binary trees running C's instruction count in 5.7× C's time. The second turned out to be `rep movsq` copying the three-word `Tree` at every match: a microcoded instruction that starts slowly, and which callgrind counts as one. Copying up to 8 words with moves fixed it ([[MYLA-246]]).

## Next

The owner weighs the results for D117 (4); [[MYLA-160]] goes on with the runtime's port, the IR's open points and a first backend. The benchmarks stay as a measure for each of the tasks above: rerun `run.py` before and after.
