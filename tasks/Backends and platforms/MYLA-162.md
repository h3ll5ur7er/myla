---
id: MYLA-162
title: The runtime off assembly - Myla runtime and a platform layer
type: feature
status: in-progress
priority: medium
labels: [runtime, platforms]
---
Second step of [[MYLA-62]]: the runtime (about 3,000 lines of hand-written x86-64 assembly in [[selfhost/codegen.my]]: the allocator with per-worker heaps, strings, maps, builders, printing and float formatting, traps, the work-stealing executor with actor executors, thread state through `%fs`, `clone`, `futex` and raw system calls) rewritten once in Myla and compiled through the IR (D117), so that a new backend only translates the IR and a new target only needs a thin platform layer. [[MYLA-160]] sizes it first. This is the step that makes other platforms affordable.

- [ ] The portable part in Myla: allocator, strings, maps, builders, formatting (byte-identical to the interpreter), traps, the executor's logic
- [ ] The platform layer behind a small interface: memory (`mmap`), output and files, processes (`__run`), directories, threads, parking and waking, thread-local state, time, exit; Linux first, with system calls as today
- [ ] Atomics where the runtime needs them (counts of actor handles, queues, the failure flag of D97)
- [ ] The x86-64 backend uses it; the gates and the bootstrap still pass, and the cost against the assembly runtime is measured
- [ ] Arenas that grow lazily (D106, [[MYLA-206]])
- [ ] The runtime out of [[selfhost/codegen.my]] (D108, [[MYLA-217]])
- [ ] Then the reactor: [[MYLA-230]] (D107)

## Sizing (2026-11-03, for [[MYLA-160]])

Measured on the sources and on two programs (the compiler; a program with tasks and actors).

- **Hand-written assembly:** about 2,700 instruction lines in 86 routines.

  | Area | Lines | Needs |
  |---|---:|---|
  | Files, directories, environment | 517 | system calls, string copies |
  | Executor, tasks, actors | 516 | atomics, `futex`, `clone`, thread-local state, jumps into frames |
  | Maps | 354 | byte compares and copies |
  | Processes (`__run`, `poll`) | 322 | system calls |
  | Strings, characters | 250 | byte copies |
  | Lists | 232 | byte copies |
  | Numbers and printing | 230 | system calls |
  | Traps, stack overflow | 111 | a signal handler on an alternate stack |
  | Allocator (per-worker heaps) | 96 | `mmap`, atomics for remote frees, thread-local state |
  | The rest (function values, deep copies, math) | 55 | |

- **Generated per type outside the IR:** about 600 lines of templates in [[selfhost/codegen.my]] (the retain, drop, clone and deep walks, function-value adapters, partial application, derived equality), 428 routines and 12,000 instructions in the compiler's own binary. A new backend would have to emit them too unless they are generated as IR functions; that is part of the port.

- **What Myla can't express yet**, and what it takes:
  - *Raw memory:* loads and stores of a width at an address, the allocator, a value's cell and back. Prototyped as primitives of the standard library (D100's `__` mechanism): `__load8`, `__load64`, `__store8`, `__store64`, `__alloc`, `__addr_of`, `__str_of`, lowered to the IR's `load`/`store` with a width (D120) and `mov`. No change to the language.
  - *Bulk memory:* copy, compare, fill as primitives each backend implements natively (`rep movsb`, `memory.copy` on wasm); `__copy_bytes` prototyped.
  - *Atomics:* exchange, compare-and-swap, add, and a spin hint, for actor handles' counts, the executor's queues and the failure flag (D97): primitives too, an IR instruction each.
  - *System calls and thread-local state:* the platform layer's job, a small set of entry points per platform.
  - *Control transfers no function makes:* starting a thread on a new stack, jumping into a frame, the executor taking its stack back after a failure, the stack-overflow handler. They stay in the platform layer, hand-written per target, a few dozen lines each.

- **What it costs** (the prototype, `tests/burn/test_raw_memory.py`): string concatenation and equality written in Myla, compiled through today's IR, against the assembly in the same program. The copy loop in Myla takes 1.9× the assembly's instructions; on the `__copy_bytes` primitive 1.32× (concatenation alone 1.21×, equality, still a loop in Myla, 2.27×). The remaining gap is instruction selection (an address computed through `%rax` instead of an addressing mode, `i += 8` in three moves, two branches per loop turn), which the optimisations of D117 (3) improve for every program, not only the runtime.

So the port is about 2,700 lines of assembly becoming Myla (minus the platform layer's few hundred), plus the per-type walks generated as IR; the language needs no change, the IR a few primitives (atomics), and the cost is about 1.2–1.3× in the runtime's hot routines until instruction selection improves.

## The way it moves (2026-11-03)

- **Where:** `lib/std/rt.my`, a module of the standard library (embedded with it, D118; its primitives silent there, D100). A native build loads it with every program (`LoadOptions.runtime`, set by `compile_asm` and `gen_main`); its functions are compiled only where called. A standard library root without it keeps the assembly.
- **How a routine moves:** the lowering calls the Myla function in place of the assembly routine (`rt_call`, `myla_runtime_function` in [[selfhost/lower.my]]); both take their arguments in `%rdi`… and return in `%rax`, the Myla convention since D119, so nothing adapts. The assembly stays while assembly routines still call it.
- **Order:** the self-contained routines first (strings, number formatting, lists, builders, maps), then the allocator (with atomics and thread-local state as primitives), then the executor and the platform layer (system calls, threads, the control transfers), then the per-type walks generated as IR instead of assembly.

## Step 1: string concatenation and equality (2026-11-03)

- `std.rt`'s `str_concat` and `str_eq`, on the bulk primitives `__copy_bytes` and `__equal_bytes`. The compiler itself calls them 2,807 and 930 times; the bootstrap reaches its fixed point; 909 tests pass (`tests/burn/test_raw_memory.py` also checks the routing and the fallback).
- **Cost:** string building 11.8% more instructions; word frequency, closures unchanged; the self-compile 3.8% more (the same output). Each call pays a frame and spills where the assembly routines are frameless leaves: the register allocator doesn't place values the way hand-written code does (a call's arguments go through the frame, two spare registers already hold the parameters). Letting a value read last by a call live in `%r10`/`%r11` gained 0.08%; the rest needs arguments coalesced into their registers and frames left out of leaf functions, the backend half of D123.

## The backend first (2026-11-03, the owner's choice (a))

Before the hot routines move, the backend gets closer to hand-written code, which every program gains from:
- **Arguments in caller-saved registers:** a value read last by a call (nothing clobbering before) lives in `%r10` or `%r11`, or `%r9`/`%r8` when the arguments loaded before it don't fill that register (`call_arg_index`, also through a variable's slot).
- **No cell for a variable living in a register** (`no_cell`), so a function without spills has an empty frame; and **no frame at all** for a function with no cells, no saved registers and no arguments on the stack (`frameless`; not under -g). 46 of the compiler's 1,304 functions.
- **`x = x op y` in place:** an integer `+`, `-`, `&`, `|`, `^` whose result only the store into the variable reads is one instruction on the variable's register (`emit_in_place`, `canonical_insn`), not a round trip through `%rax`; about 950 places in the compiler.

Measured (instructions, the same sources built before step 1 and now): the benchmarks 3.2% fewer on the geometric mean (the sieve 10.4%, Mandelbrot 7.2%, closures 6.7%, fib 5.7%), string building still 10.8% more (its concatenation in Myla); the self-compile, with its strings in Myla, 1.7% more than with the assembly routines and the old backend (it was 3.8% after step 1).
- **More of the same (2026-11-03):** `a + k`, `a - k` and `a + b` from registers into a register are one `lea` (`emit_lea`, re-extended for a signed 32-bit result); a function whose body reaches its frame nowhere, the cells its temporaries were given having stayed unused (their values never left `%rax`), has its prologue and every `leave` blanked after the body is emitted (`drop_unused_frame`). 76 of the compiler's functions set up no frame now, `std.rt`'s `str_eq` among them. The self-compile with its strings in Myla is 0.8% above the assembly routines with the old backend (it was 3.8% after step 1, 1.7% after the first round).


## Step 2: the file system (2026-11-03)

- `std.rt` makes system calls: the primitives `__syscall(n, a, b, c)` (Linux's numbers, the result or `-errno`), `__set_io_errno` (the errno `std.io` reports) and `__free`, all three known to the seed before the library uses them (a primitive goes in one commit, its first use in the next).
- Moved: `read_file`, `write_file`, `list_dir`, `stat`, `mkdir`, `unlink`, `rmdir`, `rename`, `getcwd`, the routines behind `std.fs` (about 500 lines of assembly, 200 of Myla). A program using them prints the same natively as in the interpreter (writing and reading back 200 KB, a file without a size in `/proc`, 300 directory entries, every error path).
- `getenv` too, on the primitive `__environ()` (the environment the process started with); the same answers natively and interpreted, a value holding `=`, an empty one and a name that is a prefix of another included.
- `run` (`std.process.run`'s routine, 320 lines of assembly, 150 of Myla) on two more primitives that leave its stderr and status where `__run_stderr`, `__run_exit_code`, `__run_signal` and `__run_errno` read them; `__syscall` zeroes `%r10`, the kernel's fourth argument (wait4's). The child's side between fork and exec is a function of numbers only, nothing allocated. A program running echo, a shell exiting 3 with output on both streams, one killed by a signal, a missing program, a file that isn't one, 300 KB and 200 KB on the two streams at once, prints the same as with the assembly routine; unlike it, `run` frees the C strings it builds.
- `read` and `poll`, `std.io`'s reader; reading 50,000 lines of standard input, a bad descriptor and an empty input give the same natively, interpreted and with the assembly. The primitive `__argv()` (the program's arguments as the kernel gave them) goes in with them, for `args` next.
- `args` on it: arguments with spaces, an empty one and non-ASCII ones come through unchanged.
- Cold: a few calls per program. What stays in assembly besides the hot routines: `__write` and the `__print_*` family (every print), number formatting, `__str_chars`, the u8-list helpers `run` no longer uses but the old path keeps, and the platform layer (`__panic`, `__on_segv`, the executor). Their assembly stays while a standard library root without `std/rt.my` needs it.

## Step 3: numbers as text, and conditions as branches (2026-11-03)

- `uint_to_str` and `int_to_str` (behind `format` and `{}`) in `std.rt`: the digits counted against powers of ten, the cell allocated at its size and filled from the end; a negative number takes its `-` in the same cell, where the assembly concatenated two strings. Every width's extremes print the same natively and interpreted.
- **Cost:** 125 instructions more per `format("{}", n)` (630 against 505), the self-compile 0.35% more. The code the routines compile to showed why: a `while` on `a && b` computed a bool (two constants, a test) before branching.
- **So, in the backend:** the condition of an `if`, a `while` or a match guard goes straight to its targets through `&&`, `||` and `!` (`branch` in [[selfhost/lower.my]]), no bool in between. The self-compile 4.164 → 4.070 billion instructions (2.3% fewer), now 1.9% below the assembly routines with the old backend; the benchmarks 0.21% fewer on the geometric mean (string building 1.5%, word frequency 0.8%, quicksort 0.3%; the others don't branch on `&&` in their loops). `tests/burn/test_selfhost_codegen.py` checks that such conditions make no bool (the function it compiles is 122 lines before, 70 after).
