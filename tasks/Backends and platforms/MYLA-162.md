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

