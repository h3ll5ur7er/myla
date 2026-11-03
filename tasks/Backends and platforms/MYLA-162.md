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

