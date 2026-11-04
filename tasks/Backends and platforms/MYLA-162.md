---
id: MYLA-162
title: The runtime off assembly - Myla runtime and a platform layer
type: feature
status: review
priority: medium
labels: [runtime, platforms]
---
Second step of [[MYLA-62]]: the runtime (about 3,000 lines of hand-written x86-64 assembly in [[selfhost/codegen.my]]: the allocator with per-worker heaps, strings, maps, builders, printing and float formatting, traps, the work-stealing executor with actor executors, thread state through `%fs`, `clone`, `futex` and raw system calls) rewritten once in Myla and compiled through the IR (D117), so that a new backend only translates the IR and a new target only needs a thin platform layer. [[MYLA-160]] sizes it first. This is the step that makes other platforms affordable.

- [x] The portable part in Myla: allocator, strings, maps, builders, formatting (byte-identical to the interpreter), traps, the executor's logic
- [x] The platform layer behind a small interface: memory (`mmap`), output and files, processes (`__run`), directories, threads, parking and waking, thread-local state, time, exit; Linux first, with system calls as today
- [x] Atomics where the runtime needs them (counts of actor handles, queues, the failure flag of D97)
- [x] The x86-64 backend uses it; the gates and the bootstrap still pass, and the cost against the assembly runtime is measured
- [x] Arenas that grow lazily (D106, [[MYLA-206]])
- [x] The runtime out of [[selfhost/codegen.my]] (D108, [[MYLA-217]])
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
- **A product by a constant** from a register is one three-operand `imul`: into the result's register, into `%rax`, or in place for `x = x * k` (`emit_imul_const`, `emit_in_place`), where it was a move into `%rax`, an `imul` there and a move out. `format("{}", n)` 634 → 607 instructions, string building 2.5% fewer, the self-compile flat (it rarely multiplies by a constant); `tests/burn/test_selfhost_codegen.py` checks the three forms.
- Tried and dropped: removing the remaining moves of a register to itself (about 200 in the compiler, none in a loop) cost more in the compiler's own emission than they saved.

## Step 4: a string's characters (2026-11-03)

- `str_chars` (`chars()`, which the lexer runs over every source file) in `std.rt`, on four more primitives: `__load32`/`__store32` (a `char` element's width) and `__list_addr`/`__list_of` (a list's cell, and a cell taken over as the list type the context expects). Valid and malformed UTF-8 (overlong forms, surrogates, beyond U+10FFFF, cut short, pushing onto the result) give the same natively, interpreted and with the assembly.
- **Cost, and the backend:** first 1.5× the assembly's instructions a character (24.1 against 16.0, the self-compile 0.67% more). What it compiled to showed, and the backend now does:
  - a 64-bit sum read only by the load right after it is that load's addressing mode, `off(x,y)` (`emit_add_load`); the pair rules share one match of the first instruction (`emit_pair`: three calls copying each instruction had cost the compiler 17.6 million instructions);
  - a widening cast of an unsigned value, or of a signed one to a signed type, re-extends nothing (a register holds its value extended from its width);
  - a shift by a constant is an immediate, not a count through `%cl` and a mask.
  And `str_chars` keeps its loop small: the multi-byte sequences are decoded by a function of their own (`decode_at`), so the loop's five values stay in registers where the allocator had given them to the cold path's (a nested loop weighs more).
- Now 18.8 instructions a character, 1.17× the assembly; the self-compile 0.3% above the assembly routines (4.083 against 4.071 billion); the benchmarks unchanged or slightly better (word frequency 0.27% fewer, quicksort 0.20%). `tests/burn/test_selfhost_codegen.py` checks the shifts, the widenings and the folded address.
- **Two more registers:** `%rsi` and `%rdi` hold values whose interval has no call and no copy (the one other instruction using them, `rep movs`), as `%r8`-`%r11` hold those with no call (`clobber_kind`, one match an instruction, since passing one copies it). A loop of six values touches no frame cell now; the compiler's own code takes 0.27% fewer instructions, the benchmarks are unchanged but string building (1% fewer), whose loops already fit in nine registers. `%rcx` and `%rdx` stay the emitter's scratch (shifts, division).
- Still in the way of hand-written code: a cast's result held in `%rax` rather than standing for its source, and a callee-saved register saved for a value whose uses all became in-place forms.

## Step 5: a map's lookup (2026-11-03)

- `map_lookup` (`m[k]`, `contains`, the compiler's symbol tables) in `std.rt`, with the hash of a string's cell (`str_hash`) computed bit for bit as the assembly's `__map_hash`, which the other map routines (insertion, growth, removal, the keys) still use. A stress program (integer, narrow and string keys, removals leaving tombstones, growth, the empty string) prints the same natively, interpreted and with the assembly.
- **Cost:** first the self-compile 0.94% more. What helped: a value's probe loop of its own, the hash inline, no call in it, so its values stay in caller-saved registers; a string's hash computed once before its loop; and in the backend, `while true` jumps back with nothing tested (`branch` on a literal), which every such loop gains (6.7 million instructions in the self-compile). Tried and dropped: comparing the bytes in the loop instead of calling `__equal_bytes` (a bool made each word: 3% more on word frequency).
- Now the self-compile 0.3% and word frequency 0.36% above the assembly lookup. A string hash's rotation is one `rol` now (the primitive `__rotl`; it saves little, the compiler's names being mostly shorter than eight bytes). What remains is, in a string's probe loop, two values in the frame (the `__equal_bytes` call needs seven across it, five callee-saved registers hold them).


## Where the backend stops the port (2026-11-03)

Tried and set aside, as the way the remaining hot routines meet the backend:
- **The string builder's append** (`__sb_append_bytes`) in Myla: the self-compile 0.47% more, string building 0.6% (39.7 million instructions of string building's 163 million are its copies). With the growth inline, every value lives across a call, and those read only twice or three times don't earn a callee-saved register (`REG_MIN_USE`), so they go to the frame; with the growth a function of its own (the full builder's case a tail call), they still do, because an interval is one range in emission order: a value read after the growth's block counts the growth's call as crossing it.
- **Holes in an interval for a block that leaves the function** (a call there doesn't count against a value it doesn't read after it): the arguments of a call are loaded one by one, so a value it reads may only sit in `%r10`/`%r11` then, not in an argument register (the first try miscompiled stage 2 exactly so); and the computation cost the compiler 58 million instructions, the generated code 1% more (values crowding `%r10`/`%r11`).

So what the hot routines left (map insertion and growth, builders, list growth, the allocator) need from the backend is the register allocation of D123's second half: live ranges with holes and splitting on the SSA form ([[MYLA-254]]), and argument moves done as a parallel move. That is the next backend step; until it is done, those routines stay in assembly.
- **Done since, as a first part:** a call's arguments are one parallel move when one sits in the register of an argument loaded before it (`load_words`, used by calls, runtime calls and tail calls; one by one otherwise, which keeps a value held back in `%rax` going straight to its register), so a value a call reads last may now live in any caller-saved register, its own argument register first (a function value, read after the arguments, still `%r10`/`%r11`). The allocator also learnt that a call in tail position with owners dropped after it has those drops emitted before it (`replacing_call`), which the wider rule exposed (a self tail call's first argument clobbered by the drop). The benchmarks 0.45% fewer instructions on the geometric mean (Ackermann 2.7%, string building 1.85%, binary trees 0.43%), the generated compiler 0.54% (the self-compile flat, the allocator's extra work included); `tests/burn/test_selfhost_codegen.py` checks swapped and rotated arguments.

## Step 6: the string builder's append, on the new allocator (2026-11-03)

With lifetimes that have holes ([[MYLA-257]]), `sb_append` (the full builder's case a function of its own, `sb_append_grown`) compiles to a frameless function of 13 instructions and the copy: the self-compile 0.37% fewer instructions than with the assembly routine, string building 0.9%, word frequency 1.8%.

- **Map insertion** (`__map_set_slot`, its two results in one word, the slot's low bit telling whether the key was there) tried on the new allocator and set aside: the self-compile 0.34% and word frequency 0.5% above the assembly, a string key's probe loop keeping five values in the frame around its `__equal_bytes` call. It waits for values saved around the calls they cross instead of living in the frame ([[MYLA-257]], splitting).

## Step 7: printing and a map's keys (2026-11-03)

- `print` of a string, an integer, a bool or a char (`print_str`, `print_int`, `print_uint`, `print_bool`, `print_char`; a float keeps the assembly), `std.io.write` (`write`) and `keys(m)` (`map_keys`, each key at its rank, as wide as the list's elements) in `std.rt`. A line and its newline still go out in one `writev`, so the lines of tasks on other workers don't interleave (the concurrency suite's long lines included). A program using maps of string, `int16`, `char`, `uint8` and `int64` keys prints the same natively, interpreted and with the assembly.
- **Cost:** a print takes about 215 instructions in user space where the assembly took 65 (the `writev` vector and an integer's digits are allocated and freed now, where the assembly used its stack), the time the same (the system call dominates: 62 against 59 ms for 400,000 prints); the self-compile 0.24% more. A scratch buffer per worker would take the allocations away (with the allocator's thread-local state).
- `__write_err` and `__write_err_num` stay with the traps they serve (the platform layer).

## Step 8: the allocator, without tasks (2026-11-03)

- `alloc` and `free` in `std.rt`, on four more primitives: `__rt_addr("sym")` and `__rt_get("sym")` (a runtime variable's address and value, a worker's own with tasks), `__bsr64` and `__trap_oom`. Without tasks the names `__alloc` and `__free`, which the rest of the runtime calls, are `.set` to them, the codegen requests them, and `_start` maps the arena before `main` (`__heap_init`), so `alloc` checks nothing on every call as the assembly did. With tasks the assembly stays (each worker's heap, the cells freed on another worker returned to it): that needs atomics as primitives.
- **Before:** the comment and [[Architecture/Native-backend]] said `__free` clobbers only `%rax`. Making `__alloc` and `__free` overwrite every caller-saved register before returning, the bootstrap reached its fixed point and the whole suite passed: no caller relies on more than the C convention, so a Myla function can be the allocator.
- **Shaped for the backend:** the out-of-memory call after the function's return, so nothing is live across it (the allocator is a leaf, without a frame); a store of a literal evaluates the literal first so the address folds into the store (`movq $1, -8(%r9)`), and a sum or difference with a constant folds into a store as into a load.
- **Measured:** the self-compile 0.12% fewer instructions than with the assembly allocator; the benchmarks (against the new allocator's, MYLA-257) 0.76% fewer on the geometric mean, binary trees 2.6%, word frequency 3.3%, string building 2.6% (with this round's routines); peak memory the same.
- **With tasks too:** `alloc_tasks` and `free_tasks`, on `__cas64`, `__xchg64` and `__rt_waddr("sym", w)` (worker `w`'s own of a runtime variable). A cell freed on another worker goes onto its owner's `__remote_free` with a compare-and-swap; the owner takes the list whole (`alloc_drained`, out of the fast path) before it bumps its arena. Each worker sets up its arena when it starts (`_start` for the first, before the others start). A runtime variable that isn't a worker's own (`__heap_base`) is next to `%rip` with tasks too, where `tv()` had given `%fs:0`. The whole suite passes, the concurrency stress tests three more times on 1, 4 and 16 workers and in every order; a program allocating in three tasks takes 0.7% fewer instructions than with the assembly. No allocator is left in assembly but `__heap_init` (the mapping).


## The executor, studied (2026-11-03)

A read-only study of the executor in assembly before its port, the order:
1. `__sched_init` and `__workers_count` (cold, no allocation; they run before the arena exists).
2. The leaves: cancel, cancelled, waking the waiters, waiting for the stopped workers, `__task_exit`, routed like the rest of `std.rt`.
3. The queues as a unit (lock inline, push, yield's push, find, peek): about 72 instructions per frame scheduled today, 41% of a task-heavy program, so the own queue's fast path stays a leaf with the lock inline.
4. The actor's enter and leave.
5. The loop itself, over a small platform layer (`__exec_enter` saving the callee-saved registers and `%rsp`, `__exec_abandon` taking it back after a failure) and the entry points that resume a frame in place without growing the stack.
6. Starting the threads, over a platform `spawn` (clone).

It needs a few more primitives: an atomic add (`lock xadd`), `pause`, and loads and stores marked as ordered so no later optimization caches them in the spin loops. The executor may not allocate (a failure is reached from the allocator's out-of-memory) nor trap holding a lock.

**A bug it found, fixed:** `task.cancelled()` looked at the task of `__exec_cur`, the frame the executor resumed last. That frame can end and be freed while its task goes on in its caller; when a new child's frame took its memory and was cancelled, the parent looked cancelled natively (`true` on 1 and 4 workers, `false` in the interpreter). The executor now records the task's first frame when it resumes one (`__exec_task`, word 104 of a worker's block), which stays the same until control comes back. Regression test: `t17_cancelled_after_an_await` in the concurrency stress tests. The study also found `__actor_held` written but never read; it goes with the actor's port.

## Step 9: the executor's start (2026-11-03)

- `sched_init` (MYLA_SCHED) and `workers_count` (MYLA_THREADS, else the CPUs from `sched_getaffinity` into a static `__cpu_mask`) in `std.rt`, allocating nothing (they run before the arena is mapped): `rt_exec` lists the executor's routines std.rt has, the codegen requests them and `.set`s the runtime's names to them, as for the allocator.
- **Checked against the assembly** on a program that counts its threads (`/proc/self/task`) and prints its tasks' order: the same count for no MYLA_THREADS, `0`, `1`, `3`, `33`, `abc`, an empty value, `100001` and `2x`, and the same order on one worker for `fifo`, `fifox`, `seed:`, `seed:1`, `seed:7`, a seed past 2^64 (it wraps) and `MYLA_SCHEDX`.

## Step 10: cancellation and the wait for the stopped workers (2026-11-03)

- Two primitives first, with the seed: `__fetch_add64(p, v)` (`lock xadd`, the value before) and `__pause()`, inline, for the executor's counters and spin loops.
- `task_cancel` (a compare-and-swap loop for the `lock or`), `task_cancelled`, `failed_wait` and `wait_stopped` in `std.rt`, through `rt_exec`. The compiled callers already treat them as calls clobbering every caller-saved register, the assembly callers (`__panic`, `__task_exit`) keep nothing in one across them. `__wake_waiters` and `__task_exit` wait for the queues and `__task_fail`, which they call.
- The concurrency stress tests, scheduling, yield and native runtime tests pass (the failure tests t08 and t15 go through `failed_wait`), and the cancellation probes print the interpreter's answers on 1 and 4 workers.
- Seen in the code: `x & k` tested against 0 is `and`, `cmp $0`; one `test` would do (backend, later).

## The backend for the queues (2026-11-03)

The executor's queues in Myla (`exec_push`, `exec_find` and the rest, the next step) first cost 40% more instructions than the assembly on a task-heavy program (125.4 M against 89.4 M): small helpers called, not inlined, values across those calls on the stack, constant expressions computed at run time. Following choice (a), the backend first ([[Architecture/IR]] has the list): an inliner for small leaf functions of the caller's module (`selfhost/inline.my`, off under `-g` and with `--no-inline`, which the tests of one function's code pass), the blocks one jump reaches joined to it, constant folding, `__trap_oom()` as a terminator, scaled-index addresses, compares with a memory operand, operations in place in the result's register and a few smaller ones. With them the same queues take 95.0 M (+6% over the assembly); the benchmarks run 0.86% fewer instructions on the geometric mean, none more; the compiler compiling an older source of itself 1.67% fewer.

## Step 11: the executor's queues (2026-11-03)

- `exec_push`, `exec_yield_push`, `exec_find` (with `exec_steal`) and `exec_peek` in `std.rt`, through `rt_exec`, on `__xchg64` (the lock, now 8 bytes), `__fetch_add64`, `__pause` and the futex through `__syscall`; nothing allocates, and the lock is given back before the out-of-memory trap. `__exec_run` takes the found frame from %rax.
- **Measured** on the task-heavy program (100k `async let`, actor calls and yields): 95.0 M instructions against the assembly's 89.4 M (+6%, with the backend work above; 125.4 M before it); its wall time on 4 workers the same within noise, on one worker 11% more of 23 ms. What is left of the gap, in the generated code: a temporary loaded from a variable gets a register of its own when it lives across blocks, even though the variable isn't written meanwhile (copy coalescing by value); a result stored in a variable and loaded for `ret` makes a round trip through a register; `lock add` and `leaq` of a runtime variable could take its address as the operand.
- The concurrency stress tests, scheduling, yield and native runtime tests pass, three times in a row.

## Step 12: waiting for a task and the actors (2026-11-03)

- `task_wait`, `wake_waiters`, `actor_enter` and `actor_leave` in `std.rt`. `myla___wait` and `myla___actor_enter` stay as stubs of the platform (call the Myla function; resume the frame it returns, or return to the executor on 0), as the jump into a frame isn't a function's. `__actor_held` is gone: written on every actor entry (a runtime call) and never read.
- **Measured** on the task-heavy program: 97.0 M instructions (95.0 M before: the stubs' calls and the C convention's moves; the assembly's own 89.4 M). Seen in the code: a `__cas64` tested by a branch is `sete`, `movzbl`, `test`, where the `jne` after the `cmpxchg` would do.
- The concurrency stress tests, scheduling, yield and native runtime tests pass three times in a row, the whole suite once.

## Step 13: the executor's loop (2026-11-03)

- `exec_run` (the loop) and `exec_idle` (the spin and the futex sleep) in `std.rt`, on one more primitive, `__run_frame(fr)` (a call through the frame's first word; frame functions keep the callee-saved registers). `__exec_run` is a stub of the platform: it records the worker's stack (`__exec_sp`) and calls the loop; a failed task's worker (`__task_fail`, `.Lexec_failed`) goes back onto that stack and into the loop's start, which keeps nothing from one frame to the next, so resuming a frame saves no registers. `__exec_idle` and `__exec_sleepers` are 64-bit counts now (only Myla touches them); the futex still compares `__exec_seq`'s low half.
- Two backend steps for it: a `__cas64` a branch tests is its `cmpxchg` and a jump on ZF; a runtime variable's address that only loads, stores and atomics read is no instruction, they name the variable (`%fs:k`, `sym(%rip)`).
- **Measured** on the task-heavy program: 96.3 M instructions against the assembly's 89.4 M (+7.7%), the same wall time on one worker (20.3 ms against 21.1 ms) and on four (0.59 s each). The "every task waits for another one" error is the loop's safety net no program reaches today (structured concurrency, MYLA-148); it is untested, as before.
- What is left of the executor in assembly: the platform's part (`_start`'s setup, starting the threads, `__task_fail`'s claim and the stack switch, the entry points that jump into a frame: `myla___resume`, `myla___finish`, the stubs of `myla___wait` and `myla___actor_enter`, `myla___yield`) and `__task_exit`.
- The concurrency stress tests, scheduling, yield and native runtime tests pass three times in a row, the whole suite once.

## Step 14: no assembly for what std.rt replaced (2026-11-03)

- The assembly of a routine `std.rt` stands for (`rt_has`: `myla_runtime_function` names it and the program has it) is no longer emitted, unless other assembly calls it: the file system, processes (with `__u8list_*`, only `__run` used them), standard input, the arguments, number formatting (`__str_concat` too, which only the assembly `__int_to_str` still called), a string's characters, a map's keys and the printing of every scalar but a float. A float is printed through `__print_str`, which is then `.set` to std.rt's `print_str`; `__print_line` (the float runtime's) and `__bool_to_str` (whose name the lowering builds) stay.
- Found with an offline reachability check of the assembly (from `_start` and the compiled functions, through every routine a kept one names or falls into): in a task-heavy program 2,285 of its 2,590 runtime lines were unreachable, now 816 of 1,121.
- A hello-world program's binary went from 20,968 to 11,840 bytes, the task-heavy one's from 28,808 to 23,720. `test_byte_copies` now checks the copy std.rt's concatenation goes through (`__copy_bytes`).

## Step 15: a list's growth (2026-11-03)

- `list_grow` in `std.rt`, `.set` for `__list_grow` in every program (the code generator calls it by name when a push finds the list full; `Append` already keeps its operands out of the registers a call clobbers).
- **Measured:** the benchmarks the same (+0.04% on the geometric mean); compiling the compiler 0.28% more instructions, as the asm's `rep movsb` (valgrind counts it a byte at a time) became `__copy_bytes` (8 bytes a turn under 512); the time the same within noise. Seen on the way: growing lists copies about 5% of the compiler's instructions; growing in place at the arena's end, when the cell is the last one allocated, would save most of it (later).

## Step 16: a map's insertion and growth (2026-11-03)

- `map_put_slot` (room made and the key's slot found or made, in one call: the slot's address plus 1 when the key was there, slots being 8-byte aligned), `map_set_slot`, `map_rehash`, `map_new` and `map_rebuild` in `std.rt`. The lowering calls `map_put_slot` in place of `__map_reserve` and the `RtPair` of `__map_set_slot`; `__map_new` and `__map_rebuild` (which `remove` calls) are `.set` to std.rt's. The assembly's `__map_new`, `__map_set_slot`, `__map_grow`, `__map_rebuild` and `__map_reserve` are gone from programs with std.rt; `__map_lookup`, `__map_hash` and `__key_eq` stay for `remove` (its lookup is still in assembly).
- On the way, in the backend (previous commit): the inliner counts only what a function's entry reaches and takes a little more (16 blocks, 32 instructions); a 64-bit multiply and a rotation by a constant work in place.
- **Measured:** word frequencies 0.55% more instructions than with the assembly maps (the rest of the benchmarks the same, +0.05% on the geometric mean): the assembly compared a string key's words inline before calling `__equal_bytes`; compiling the compiler 0.05% fewer. A first version, with the hash and the comparison in helpers, cost 2.1% (the inliner then took neither).

## Step 17: the builder's appends (2026-11-04)

- `sb_append_byte` (`append_byte`, called in place of the `SbAppendByte` instruction, which passed the byte through the stack to the general routine) and `sb_append_bytes` (`.set` for `__sb_append_bytes`, a string range's append) in `std.rt`, with `sb_append`; the asm `__sb_append_bytes` is gone from programs with std.rt.
- **Shape matters:** with the growth called in the middle of each function, the fast path's values lived across a call (callee-saved registers on every append): string building +1.1%, word frequencies +1.0%. With a full builder handled by a tail call (`sb_append_grown`, `sb_byte_grown`), the fast paths call nothing: word frequencies 0.39% fewer instructions than with the assembly, string building the same, compiling the compiler 0.31% fewer.

## Step 18: a character's and a bool's text, `remove`'s lookup (2026-11-04)

- `char_to_str` (a character's UTF-8 bytes) and `bool_to_str` (a literal, retained as a returned literal is) in `std.rt`, routed by `myla_runtime_function`; `__map_lookup`, which `remove` calls, `.set` to std.rt's `map_lookup`, so the asm `__map_lookup`, `__map_hash` and `__key_eq` go too (`__str_eq` stays: the float runtime calls it).
- The compiler's own binary now carries 124 lines of runtime assembly no code reaches (offline check), all in helpers the code generator emits for any program that might need them (function composition, a float's printing, a few primitives' stubs).
- What is left of the hand-written runtime besides the platform layer: float formatting, `__str_eq`, `__print_line`, function values (`__compose_*`, `__func_*`); the per-type routines (`__sb_clone`, `__str_drop`, `__sb_drop` with them) are the next step's.

## Step 19: floats as text (2026-11-04)

- `float_to_str`, with `fscale` and `two_prod` (Dekker's product, returned as a tuple), in `std.rt`, on one more primitive, `__f64_round` (`cvtsd2si`, ties to even). Each floating-point operation is the assembly's, in its order. A program that makes a float text asks for it once its functions are emitted (`wants_ftoa`: the worklist runs again), and `__float_to_str` is `.set` to it; of the float runtime only `__fmod` stays in assembly.
- **Checked bit for bit:** 900,020 floats (random bit patterns as float64 and float32, ordinary numbers, subnormals, the extremes) print the same as with the assembly, and 9,020 of them the same as the interpreter.
- **Measured:** that program's time the same as with the assembly (220 ms against 221 ms over five runs). One division a digit (`q = m / 10`, the digit `m - q * 10`) matters: with `m % 10` and `m / 10`, two `div`s, it took 241 ms, though fewer instructions; valgrind's instruction count misleads on `div`.
- Seen in the code: a `while` loop tests at its top and jumps back from its end, a jump a turn more than a loop tested at its end (backend, later).

## Step 20: the per-type routines as IR, first derived equality (2026-11-04)

The code generator's per-type routines (retain, drop, clone, the deep walks, derived equality, function-value adapters: about 12,400 instructions in the compiler, 3.9%) were assembly templates; a new backend would need its own copy of each. They move to IR functions, built in `selfhost/lower.my` (`routine`: a lowering without source) and emitted by `emit_routine` (the verifier, the inliner, `emit_ir_at` under the type's declaration).

- **Derived equality first** (`derived_eq_ir`): `#derive(Eq)`'s `T.eq` field by field, or tags then the payload of the variant both have, each component as `==` compares it (a struct or enum by its own `eq`, a boxed one's cell passed; strings through `str_eq`; floats as floats; anything else as 64 bits). It was already called as an ordinary function. An enum with a payload's `eq` is now 14 instructions where the template's took more (no frame, operands in registers); compiling the compiler the same.
- The order for the rest (from a study of the families): the walks `__walkd_`/`__walkr_` (4,700 instructions, straight-line code and a tag switch), `__dropb_`, the list and map drops, the copy-on-write clones, the deep copies, the environments' routines (an inline-semantics drop at an address is missing from the IR; `__deep_env` jumps through two words before `_env_drop`), the thunks and composition. Traps on the way: a drop's fast path (count down, not zero: return) runs before any prologue today, and an IR function saves its callee-saved registers first; `DropAt` drops a member (a boxed value is a pointer) while `Retain` retains an inline value; a clone's decrement has no zero check (the caller saw a count above 1).

## Step 21: the walks as IR (2026-11-04)

- `__walkd_<T>` / `__walkr_<T>` (release or retain every heap value an inline struct, tuple or enum holds) are built as IR (`walk_ir`) and emitted under their own names (an alias of `myla___walkd_<T>`): a cell or boxed member is `LoadAt` and `retain T %v` or the new `drop T %v`, an inline aggregate or function value `Retain`/`DropAt` at its address, an enum's tag a chain of compares. The parameter's slot is read afresh at each use, so it lives in a callee-saved register from the entry and each read is that register.
- **What it took to match the templates** (the first version cost the compiler 3.1% more instructions, binary trees 6.4%): `DropAt` passed a leaf through `%rbx` pushed and popped around it (now `drop T %v`); a load's one reader couldn't take a load whose source read %rax; `Retain` and `DropAt` weren't known to read their address before their one call, nor `retain T %v` to call nothing, so their operands took callee-saved registers that the prologue saved for nothing; the callee-saved threshold was 12. With those (the previous commits), binary trees runs the same instructions as with the templates, the other benchmarks too, and compiling the compiler takes 0.25% more (a few hundred walk routines, each a little longer at its entry).

## Step 22: the drops as IR (2026-11-04)

- `__dropb_<T>` (a boxed enum's or an actor's cell), `__drop_list_<E>` and `__drop_map_<K>_<V>` are each two IR functions: an entry counting the cell down (`__rc_dec`, an inline `decq`, `lock decq` for an actor with tasks, its zero flag what the branch tests) that returns, or at 0 jumps to its slow path (a tail call; the entry makes no call, so it has no frame); and the slow path, which releases what the cell holds (a boxed enum's walk in place, not called; a list's elements and a map's occupied slots in a loop) and frees the cell with a tail call to std.rt's `free`.
- **Measured:** binary trees 7.3% fewer instructions than with the templates (a boxed enum's drop no longer calls its walk), the benchmarks 0.78% fewer on the geometric mean; the compiler's own code 0.84% faster on the same input, but its routines built and allocated as IR cost it 1.1% more work: compiling the compiler 0.29% more.

## Step 23: the copy-on-write clones as IR (2026-11-04)

- `__clone_list_<E>`, `__clone_map_<K>_<V>` and `__sb_clone` are built as IR (`clone_ir`): the cell copied with `__copy_bytes` (in place of each template's own copy loop), each element or occupied slot retained (`each_entry`), the original counted down (`__rc_dec` with no result). `__str_drop` and `__sb_drop` are drop entries whose slow path is std.rt's `free` itself. A list or map whose entries own nothing has the builder's clone and drop (`.set` to them; 32 routines fewer in the compiler).
- **Measured:** the benchmarks the same (none clones much); the clones' code about the same as the templates'. But each routine built as IR costs the compiler what compiling a function of its size costs: compiling the compiler 1.1% more for the 85 clones it keeps (allocating registers, rematerializing, live ranges). With the walks and drops, the per-type routines as IR cost the compiler about 1.6% more work so far, against code 0.8% faster and binary trees 7% faster: a cheaper backend for small functions is the obvious follow-up.

## Step 24: the deep copies as IR (2026-11-04)

- The deep copies values crossing between tasks get (D92): `__deepw_<T>` / `__dclonew_<T>` (an inline value's members), `__deepi_<E>` / `__dclonei_<E>` (a boxed enum's cell contents) and the cells' `__deep_list_`, `__deep_map_`, `__deepb_`, `__deep_sb` and their clones, built as IR (`deep_walk_ir`, `deep_cell_ir`): a member's cell copied deeply and stored back, a function value's environment through the fixed runtime's `__deep_env`, an actor handle shared (a clone retaining it), a shared cell copied first (its clone, or a boxed enum's box with what it holds retained). The builders return the routines they call (`Want`), which the code generator then requests (`emit_wanting`); a routine calls another by the name its alias gives it (`Rt`), as shared ones exist only as aliases.
- The compiler has no tasks, so only the tests run these: the whole suite, the concurrency stress tests, scheduling and native runtime tests three times more.

## Step 25: the environments' routines as IR (2026-11-04)

- A lambda's or partial application's `myla_<lifted>_env_drop` is built as IR (`env_drop_ir`): each capture it owns released as it is held inline (a cell loaded and `drop T %v`; a function value's environment through `__func_drop`; an inline aggregate `DropAt` at its address; a boxed enum, whose capture the template walked as a value, its walk called at the address), then the cell freed with a tail call to std.rt's `free`. With tasks, `_env_deep` and `_env_clone` too (`env_deep_ir`, sharing the deep copies' `deep_member`), emitted with the two words `__deep_env` and `__dclone_env` read just before the drop label.
- **Measured:** compiling the compiler and the benchmarks run the same instructions (the routines' code the same length as the templates'). Nothing tested an environment's deep copy or clone before: `t18_closures_cross_tasks` hands closures (capturing a string, a list, a struct and another closure) to children and shares one between siblings; it gives the same output as with the templates, and valgrind finds nothing.
- A composition's environment (`l >> r`: two function values) has the same routines, built by the same builders (`__compose_env_drop`, its deep copy and clone). `__compose_call`, the function-value adapters (`__fnval`) and the partial applications' thunks stay in the backend: they are calling-convention glue (the environment in `%r10`, argument words rebuilt below the frame, a jump that keeps the stack flat for `become`, MYLA-130), which the IR doesn't express and each backend writes like its prologues. Building the composition's routines for every program costs compiling hello 0.2%.


## Step 26: the assembly fallbacks deleted (2026-11-04)

- A native build loads std.rt always: a standard library folder without `std/rt.my` gets the copy the tools carry (`<myla>/std/rt.my`, its module still `std.rt`). So every gate on std.rt being there (`rt_alloc`, `rt_has`, `asm_prints`, `rt_exec_has`, the `has_func("std$rt$…")` checks) was always true, and the assembly each guarded is gone: the allocator, `__str_drop`, `__sb_drop`/`__sb_clone` and the environments' routines as templates, the printing, number formatting, `__bool_to_str`, `__char_to_str`, the file system, processes, standard input, the arguments, a string's characters, a map's keys, lookup, insertion and growth, the builder's append, a list's growth, the executor's queues, loop, start, cancellation and waits, the float formatting (`__float_to_str`, `__two_prod`, `__fscale`: only `__fmod` stays) and `__print_line`, which nothing called any more. With them, every helper only they used.
- `codegen.my` went from 8,794 lines to 5,599. Every example, benchmark and stress test compiles to the same assembly as before but for `__print_line`'s absence; the compiler compiles to the same assembly. Its binary is 6% smaller, and compiling it takes 5.3% fewer instructions (less of it to compile).
- What stays in assembly: the program's start, the traps and the panic, `__write_all`, the stack-overflow handler, `__str_eq` and the other routines assembly still calls, the system-call and memory primitives, the per-worker heap setup (`__heap_init`), the thread start and the jumps into frames, `__func_retain`/`__func_drop`, and the calling-convention glue (`__compose_call`, the function-value adapters, the partial applications' thunks).

## Step 27: the strings' deep copies (2026-11-04)

- `__deep_str`, `__dclone_str` and `__dclone_cell` (a cell owning nothing made unshared, or copied, for a value crossing between tasks) are std.rt's `deep_str`, `dclone_str` and `dclone_cell`, requested with the executor's (`rt_exec`). `__deep_env` and `__dclone_env` stay in assembly (they jump through the words before an environment's drop function), but an environment owning nothing now goes to `__deep_str` instead of a copy loop of its own.
- **Measured** (one worker): the stress programs t05 and t18 run 2.2% and 2.8% more instructions by valgrind's count, which counts the template's `rep movsb` as one instruction against `__copy_bytes`' word loop; their wall time is the same within noise (t05 4.2–4.3 ms against 4.4–4.5, t18 2.3–2.4 against 2.3). The stress tests pass three times in a row, the suite once.

## Step 28: the ownership instructions made plain before the backend (2026-11-04)

- `selfhost/ownership.my` (`expand_ownership`, run in `emit_ir_at` after the optional SSA promotion): `retain`, `drop` (of a value, at an address, of a slot), `cow`, `deep` and `clone` become loads, `rt __rc_inc`/`__rc_inc_atomic`, and calls of the per-type routines it requests (the walks, the drops, the clones, the deep walks, `__func_retain`/`__func_drop`); `cow` becomes `rt __cow:<clone routine>`, still emitted inline. The x86 translation no longer decides anything by type for these: its cases for them are an internal error, `emit_offset_rc` and the tail-drop emission are gone (`hoist_tail_drops` moves the owners a tail call drops before the call first, under the translation's own conditions), and one classifier (`rt_internal`) tells the inline runtime operations from calls.
- **Measured:** every example, benchmark and stress test and the compiler itself compile to the same assembly as before the clean-up commits but for offsets no longer computed when a drop reads through their base (the compiler's output 1,277 lines shorter); the benchmarks run the same instructions (to within 3), the stress programs t05 and t18 0.2% fewer. Compiling the compiler takes 4.0% more instructions (4,354 M against 4,185 M on the same input): the pass and its rebuilt blocks (copies and walks of instructions, about 85 M), the larger IR's register allocation and rematerialization (about 40 M), the runtime-name checks now run for every drop (about 20 M). A cheaper path for small functions in the backend, the follow-up of step 23, would pay for it.
- Still type-driven in the backend: the async functions' frame constructor (`__new`, retaining by-value arguments copied into the frame) and the function-value thunks, which are calling-convention glue (step 25).

## Step 29: the platform layer, its Myla half (2026-11-04)

- `lib/std/platform.my` (`std.platform`, imported by std.rt as `os`; embedded with the rest, so a library folder without the runtime still finds it beside the embedded `rt.my` through the relative import): every system call std.rt made, with the numbers, flags and record layouts that go with them (`stat`'s mode and size, `getdents64`'s records, `pollfd`, `iovec`), the process runner (pipes, fork, exec, poll, wait4), the CPU count (`sched_getaffinity`), parking and waking a worker (futex) and ending the process (`exit_group`). Its functions give a result or a negative errno (`EINTR`, `EAGAIN` exported for the retries std.rt keeps). std.rt has no `__syscall` left: it records the errno, builds the strings and lists, and keeps the logic.
- The interface, for the ports (MYLA-163 to MYLA-165): files (`open_read`, `open_write`, `open_dir`, `read`, `write`, `close`, `file_size`), paths (`mode_of`, `make_dir`, `remove_file`, `remove_dir`, `rename`, `cwd`), directories (`dir_read`, `dir_entry_name`, `dir_entry_size`), the standard streams (`poll_read`, `write_all`, `write_line`), processes (`run`), workers (`cpus_allowed`, `park`, `unpark_one`) and `exit`. How a port picks its version of the module waits for the code-per-target design of MYLA-245; with one platform, the module is the Linux one.
- The other half stays in the backend, per target: the program's start (stack limit, alternate signal stack, the stack-overflow handler), the heap's memory (`__heap_init`'s mmap), starting worker threads (clone) and their thread-local state, the jumps into frames, the traps' and panic's writes, `__syscall` itself and the memory and atomic primitives.
- **Measured:** the benchmarks run the same instructions; the stress programs t05, t18 and t12 0.2%, 0.1% and 0.4% more (printing and parking now a call into another module, which the inliner doesn't cross); compiling the compiler the same. The suite passes.

## Step 30: the arenas grow lazily (2026-11-04, D106 (B))

- std.rt's allocator maps a 16 MiB chunk (`std.platform`'s `map_memory`, on a new primitive `__syscall5` for mmap's five arguments) when the arena is full, and none before the first cell; a cell bigger than a chunk gets a mapping of its own. With tasks, a worker's chunks are aligned to their size (mapped one chunk bigger, the ends given back) with its number in their first word, so `free_tasks` finds a cell's owner at its address rounded down to a chunk (was `(p - __heap_base) >> 32`). `_start`'s region of a 4 GiB arena per worker, `__heap_init` and `__heap_base` are gone, and the rings of ready frames are reserved for the workers that run (`exec_workers * 8 MiB`, was 32 always).
- **Measured:** under `ulimit -v 400000` a program with tasks runs on four workers, and one mapping 320 MB in all (small cells, and growing lists up to a 128 MB cell) runs too (`test_the_heap_grows_in_chunks_under_a_small_address_space_limit`; before, both "out of memory"). The benchmarks run 20 instructions more each (the first chunk's mapping), binary trees' wall time the same within noise; compiling the compiler the same. The stress tests pass three times in a row.

## Step 31: the runtime's assembly in a module of its own (2026-11-04, D108)

- What stays hand-written for x86-64 Linux moved from `codegen.my` to [[selfhost/runtime_x86.my]] (`impl CodeGen`, 850 lines): the program's start, the traps and the panic, the system-call and memory primitives, the executor's control transfers, the environments' deep copies, composition, std.math's and the float runtime's primitives and data. The empty list, map, builder and character emitters left by the port are gone (their cell layouts kept as one comment), and so is `tls_addr`, which nothing called. `codegen.my`: 5,484 lines to 4,625 (8,794 before step 26).
- Every example, benchmark, stress test and the compiler compile to the same assembly as before the move; the suite passes.

## Step 32: runtime errors reported by std.rt (2026-11-04)

- `__panic` is a stub now: with tasks it hands the failure to `__task_fail` (which goes back to the executor for a task other than the entry's), then jumps to std.rt's `panic_report` (`panic_report_tasks` waits for the other workers first, D97), which writes `runtime error: <message>` and `  --> file:line:col` through `std.platform` and ends the process. It allocates nothing (the digits go to `__panic_buf`), so out of memory reports through it too. `__write_err`, `__write_err_num`, the assembly `__write_all` and the two message strings are gone; the trap entries stay three instructions each.
- Programs carry 35 lines of assembly more (the report compiled from Myla). The suite passes (every runtime error of the error corpus with its position, the failing-task tests), the stress tests three times in a row, and out of memory under `ulimit -v 100000` still reports.

## Where it stands (2026-11-04)

The portable runtime is Myla (std.rt), over the platform layer (std.platform); the per-type routines are IR functions; the ownership instructions reach the backend as plain operations; the heap grows lazily. What stays hand-written for x86-64 Linux is [[selfhost/runtime_x86.my]] (about 830 lines): the program's start and the stack-overflow handler, the trap entries and `__panic`'s stub, the system-call and memory primitives, the executor's control transfers (threads, frames), the environments' deep copies, composition, and the float primitives and tables; and in the backend, the function-value adapters, the partial-application thunks and the async frame constructor (calling-convention glue). "Time" in the platform list has no user yet: the runtime reads no clock. Next: the reactor ([[MYLA-230]], D107), and per target the platform's assembly and std.platform again ([[MYLA-163]] to [[MYLA-165]]).

