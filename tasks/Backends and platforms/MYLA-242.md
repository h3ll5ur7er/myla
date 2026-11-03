---
id: MYLA-242
title: "Benchmarks: the gap to C"
type: improvement
status: review
priority: medium
labels: [performance, backend, design]
---
The first input of [[MYLA-160]], de-risking D117: how far Myla's native code is from C, and where the time goes.

The owner's terms (2026-11-03): no factor is fixed in advance. Speed or size drawbacks are acceptable where they are really needed. The bar is that Myla programs should clearly *feel* faster than Python, though Python isn't measured. So the numbers inform the owner's call on D117 (4) rather than decide it.

## Method

- **Same algorithm on both sides, written plainly.** No hand-tuned C (no SIMD, no tricks), single-threaded. The Myla code is idiomatic, as a user would write it; the compiler isn't tuned for the benchmarks before they are measured.
- **Each C program in three versions:**

  | Version | Compiled with | What it shows |
  |---|---|---|
  | Idiomatic C | gcc `-O2` | The total gap |
  | C with Myla's semantics: reference counting, bounds checks, copy-on-write, division-by-zero checks, wrapping overflow | gcc `-O2` and clang `-O2` | Against Myla, what code generation alone costs; clang (LLVM) is what LLVM's optimizer would win back on the same semantics |
  | The same | `-O0` | A baseline: an unoptimizing compiler |

  The gap between the two `-O2` versions is what the language costs, which the IR has to win back itself (D117 (3)).
- **Measured:**
  - instructions, counted exactly per function with valgrind's callgrind (deterministic, so a noisy machine doesn't matter); this also attributes Myla's time to reference counting, bounds checks, calls, frame traffic and runtime routines;
  - wall time, as the median of several runs;
  - peak memory and binary size.
- **Inputs** are sized so each Myla program runs for 0.5–2 s. Each program's output is compared with the interpreter's, so the set doubles as a test.

## The programs

One per cost that matters for Myla, so every gap points at a cause:

| Program | Mainly measures |
|---|---|
| Recursive Fibonacci | Calls, the calling convention, integer arithmetic |
| Ackermann | Very deep recursion, the stack |
| Prime sieve | Indexing into lists, bounds checks, simple loops |
| Game of Life | Nested lists, copy-on-write when each generation builds a new grid |
| Binary trees | Allocating and freeing many small objects, reference counting of recursive enums |
| N-body | Float arithmetic, struct fields updated inside a list |
| Mandelbrot | A pure float loop with almost no memory: code quality alone |
| Fannkuch | Small integer arrays, swaps, permutations |
| Word frequency | Maps with string keys, string handling |
| String building | `StringBuilder`, `format`, concatenation |
| Closures and pipelines | Function values, lambdas, partial application over lists |
| Generic quicksort | Generic code made concrete, comparisons through traits |

Outside the C comparison:
- many small tasks: it measures the scheduler, against itself, with no fair C counterpart;
- the self-compile: profiled only, to see where time goes in large code.

## Steps

- [x] A first round to check the method: Fibonacci, the sieve and binary trees, in Myla and the three C versions, with the script that builds, checks and measures them
- [x] The other nine programs
- [x] Where Myla's time goes, per program (callgrind), and what each gap would need: an IR optimisation (D117 (3)), a runtime change, or nothing
- [x] The results on a wiki page, with the script that reruns them in the repository; the owner decides what follows for D117

## Evidence

- **First round (2026-11-03).**
  - `benchmarks/` holds fib, sieve and binary trees, with `myla_rt.h` and `run.py`; `tests/burn/test_benchmarks.py` keeps every version printing the same.
  - Results and findings: [[Development/Benchmarks]].
  - The method held, but needed two additions, both now in `run.py`: user and system time and page faults, because instruction counts alone hid both large gaps; and symbol names for valgrind's addresses.
  - Found and fixed: `rep movsq` for small copies ([[MYLA-246]]; binary trees 5.9 → 2.0 s, the self-compile about 20 % faster).
  - Found and filed: 8 bytes per list element ([[MYLA-247]]).
  - Code generation is at gcc `-O0`'s level: the IR optimisations of D117 (3). clang `-O2` isn't ahead of gcc `-O2` on any of the three.
- **All twelve programs (2026-11-03).**
  - Every version of every program prints the same. fannkuch(10) and n-body match the Benchmarks Game's reference results; the other expectations were computed in Python.
  - Myla takes 1.4× to 9× the time of C with Myla's semantics at gcc `-O2`, about 3× on the geometric mean, and about 1.2× gcc `-O0`'s.
  - clang `-O2` takes 1.13× gcc `-O2`'s time on the same C: LLVM isn't ahead.
  - Each large gap has a cause and a task: floats in general-purpose registers ([[MYLA-249]]), 8-byte list elements ([[MYLA-247]]), arguments on the stack ([[MYLA-250]]), loop overhead the IR can prove away ([[MYLA-251]]), the runtime's string routines ([[MYLA-252]]), and the missing square root ([[MYLA-248]]).
  - Table and details: [[Development/Benchmarks]]. In `review`: the owner decides what follows for D117 (4).
- **The first optimisation pass (2026-11-03).** The baseline is saved in `benchmarks/results/`, and `run.py --compare` shows progress against it. One pass through the findings: [[MYLA-248]], [[MYLA-249]] and [[MYLA-252]] done, [[MYLA-251]] in part, [[MYLA-247]] and [[MYLA-250]] planned. The result: 1.37× as fast on the geometric mean, 2.57× C with Myla's semantics (was 3.06×), table on [[Development/Benchmarks]].
- **Arguments in registers (2026-11-03).** [[MYLA-250]] (D119): the same time on the geometric mean, interleaved against the stack convention (fib 1.10×, the rest within the machine's spread); fib's and Ackermann's gap to C is the optimizer's work, not the convention. Results in `benchmarks/results/2026-11-03-after-250.json`, table on [[Development/Benchmarks]].
- **Packed list elements (2026-11-03).** [[MYLA-247]] (D120): the sieve 4.21× as fast and 817 → 102 MB, closures 1.39×, fannkuch 1.17×; against C with Myla's semantics 2.12× on the geometric mean (3.06× at the baseline). Results in `benchmarks/results/2026-11-03-after-247.json`.
