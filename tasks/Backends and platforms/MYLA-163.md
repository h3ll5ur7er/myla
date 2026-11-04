---
id: MYLA-163
title: "Target: Linux on aarch64"
type: feature
status: review
priority: medium
labels: [backend, platforms]
---
The first new target of [[MYLA-62]], the closest to what exists (Linux system calls, no libc), after the runtime in Myla ([[MYLA-162]]): an aarch64 backend of Myla's own from the IR (D117), with [[selfhost/ir_x86.my]] as its template.

- [x] The platform layer for Linux on aarch64 (its system call numbers and conventions, thread-local state, atomics): done
- [x] `myla build --target aarch64-linux`; the parity, stress and concurrency programs pass under qemu or on hardware, in CI if practical

## The plan (2026-11-04, the owner's choice of aarch64 first)

Why now, and what to keep from being thrown away (the owner's analysis): aarch64 is 64-bit like x86-64, so D122 (sizes per target) changes almost nothing for it, and the address and width work (D120, D121) is done. What survives the IR work still to come is instruction selection, the AAPCS64 calls, prologues and frames, ELF output and `std.platform` for aarch64 Linux. What is at risk is register allocation: [[MYLA-257]] (D123's backend half) replaces today's allocator, liveness and rematerialization (roughly 1,000 to 1,500 of `ir_x86.my`'s lines). So the aarch64 backend **keeps its allocation deliberately simple** (every temporary in a frame cell, a few scratch registers): a few hundred lines that are cheap to throw away, and [[MYLA-257]] then builds one allocator, target-independent, for both backends instead of a second copy of today's. wasm waits for D122.

Tools: `clang --target=aarch64-linux-gnu` assembles (GNU syntax), `ld.lld -static` links, `qemu-aarch64` (qemu-user) runs the programs; CI's Ubuntu runner can install the same.

Steps, each verified:
1. **Target plumbing:** a target in the code generator (`x86_64-linux`, `aarch64-linux`), `gen_main --target`, `myla build --target`; the assembler and linker per target; a test runner through qemu (skipped where it is missing).
2. **`std.platform` for aarch64 Linux:** the loader takes `std/platform_aarch64.my` for `std/platform.my` on that target (the smallest form of MYLA-245's code per target); aarch64's system calls (the generic table: `openat`, `newfstatat`, `mkdirat`, `unlinkat`, `renameat2`, `pipe2`, `dup3`, `ppoll`, `epoll_pwait`, `clone` for fork, other numbers).
3. **`ir_a64.my`:** the IR to aarch64 with the simple allocation: scalars and integer arithmetic, loads and stores with widths, compares and branches, calls (AAPCS64: x0 to x7 and d0 to d7, the rest on the stack, an aggregate result through x8), tail calls (`become`), runtime calls, traps with positions, floats in d registers; then frame functions (`suspend`, the frame in a callee-saved register) for tasks.
4. **`runtime_a64.my`:** the program's start, the trap entries and `__panic`'s stub, the system-call and memory primitives (`svc #0`, the bulk copy and compare), atomics (`ldaxr`/`stlxr`), threads (`clone`, the state block in `tpidr_el0`), the jumps into frames, the environments' deep copies, composition, the float primitives (`fsqrt`, `frintn`, a `__fmod` in std.rt, aarch64 having no `frem`).
5. **The code generator's glue for aarch64:** the function-value adapters, the partial applications' thunks, async functions' frame constructors.
6. **Parity:** the examples, benchmarks, stress and concurrency programs under qemu against the interpreter; CI.

## Progress

- 2026-11-04, steps 1 to 5 without tasks: `--target aarch64-linux` in `gen_main` and `myla build` (clang and ld.lld), the loader's `for_target` (`std/platform_aarch64.my`), [[selfhost/ir_a64.my]] (every temporary in a frame cell), [[selfhost/runtime_a64.my]], the partial applications' functions and the function-value adapters. A map's `remove` became IR in the lowering for both targets (the `mapremove` instruction and its x86-64 assembly went). Evidence: every example but `concurrency` and ten programs for widths, floats, casts, calls with stack words and `become`, partial applications by copy, maps, strings, traps, panics and exit give under qemu what their x86-64 builds give (and the interpreter); the compiler built for aarch64 makes, under qemu, byte for byte the assembly the x86-64 one makes, for either target ([[tests/burn/test_aarch64.py]]; CI installs clang, lld and qemu-user).
- 2026-11-04, tasks: frame functions (the frame in x28, `suspend`, `__new`), the executor's control transfers, `__task_fail`, worker threads (`clone`, the state block in `tpidr_el0`), the environments' deep copies, an actor's atomic count. Evidence: `examples/concurrency.my`, the 23 stress programs on 1, 4 and 16 workers (three runs each) and in the four other orders, and test_time's ten tests (timers, reads that suspend, child processes) pass under qemu ([[tests/burn/test_aarch64.py]]).
- 2026-11-04, a float `%` exact on aarch64: std.rt's `fmod` (musl's algorithm on the bits; its `#test` cases are Python's `math.fmod`, among them `1e20 % 3.0` and `2^1000 % 0.1`, which `x - trunc(x / y) * y` gets wrong).
- 2026-11-04, a stack overflow reported on aarch64 too (the 120 MiB limit, an alternate signal stack per thread, `__on_segv` with aarch64's sigcontext): on the main stack and on a worker's, once, under qemu ([[tests/burn/test_aarch64.py]]).
- Left, outside this task: `-g` ([[MYLA-259]]); a run on aarch64 hardware (qemu on x86-64 keeps x86-64's memory order, so it can't show a missing barrier); a cancel race in std.rt that the qemu runs found was fixed for both targets (see the commit `MYLA-163: a cancel can no longer slip past a sleeper`).
