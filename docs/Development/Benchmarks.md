# Benchmarks

How far Myla's native code is from C, and where the time goes ([[MYLA-242]]). This is the first input for de-risking D117: Myla gets backends of its own, not LLVM ([[MYLA-160]]).

No factor is fixed in advance: the numbers inform the owner's decision. The bar is that Myla programs clearly *feel* faster than Python, though Python isn't measured.

[TOC]

## Running them

    python3 benchmarks/run.py [name ...] [--runs N] [--no-callgrind] [--json FILE]

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

## First round (2026-11-03)

fib, the prime sieve and binary trees, on the development container (4 cores). Times are the median of 5 runs; instructions are at the smaller `profile_size`.

| Benchmark | Myla | C, gcc `-O2` | C with Myla's semantics, gcc `-O2` | Same, clang `-O2` | Same, gcc `-O0` |
|---|---:|---:|---:|---:|---:|
| fib(36): time | 103 ms | 20 ms | 20 ms | 41 ms | 106 ms |
| fib(27): instructions | 11.4 M | 6.1 M | 6.1 M | 7.2 M | 11.0 M |
| sieve(40 M): time | 1,409 ms | 208 ms | 274 ms | 292 ms | 566 ms |
| sieve(2 M): instructions | 190 M | 33 M | 91 M | 88 M | 318 M |
| sieve(40 M): peak memory | 817 MB | 40 MB | 40 MB | 40 MB | 40 MB |
| binary trees(18): time | 2,041 ms | 1,033 ms | 1,028 ms | 1,147 ms | 1,730 ms |
| binary trees(14): instructions | 753 M | 718 M | 755 M | 785 M | 996 M |

### What the round found

- **`rep movsq` for small copies ([[MYLA-246]], fixed).** Before the fix, binary trees ran C's instruction count in 5.7 times C's time. Every match on the three-word `Tree` copied it with `cld; rep movsq`, which is microcoded and starts slowly. Copying up to 8 words with moves took binary trees from 5.9 s to 2.0 s, and the self-compile from about 870 to 690 ms.
- **Eight bytes per list element ([[MYLA-247]], open).** A `[bool]` takes 8 bytes per element, so the sieve peaks at 817 MB against C's 40 MB: a capacity of 2²⁶ slots plus the previous buffer during the last copy. The 209,000 page faults cost 0.4 to 2.8 s of system time, depending on how loaded the machine is.
- **Code generation is at gcc `-O0`'s level.** fib runs as many instructions as gcc `-O0`, and its time is the same. The cost sits in each operation:
  - arguments on the stack;
  - a `movslq` after every 32-bit operation;
  - jumps to the next instruction;
  - in the sieve's loop, the list loaded from the frame for every write, the copy-on-write and bounds checks repeated each time, `!flag` through `sete`/`movzbq`.

  These are the IR optimisations D117 (3) plans, and Myla-specific ones: LLVM doesn't know the copy-on-write rule either.
- **LLVM isn't ahead here.** clang `-O2` is slower than gcc `-O2` on all three programs (fib by 2×, from how each compiles the recursion). On Myla's semantics it runs about as many instructions as gcc.
- **The remaining binary-trees gap is memory.** With the copies fixed, Myla runs C's instruction count in twice C's time:
  - 2.6× the first-level cache misses;
  - 80 MB against 34 MB: Myla's enum cell is larger than C's node, and its allocator holds more.

## Next

The other nine programs of [[MYLA-242]] (n-body, mandelbrot, fannkuch, word frequency, string building, closures, generic quicksort, Ackermann, Game of Life), then the summary for [[MYLA-160]].
