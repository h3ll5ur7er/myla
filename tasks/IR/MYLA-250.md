---
id: MYLA-250
title: Arguments and results in registers
type: design
status: in-progress
priority: medium
labels: [backend, performance, calling-convention]
---
Found by the benchmarks ([[MYLA-242]]): call-heavy code runs at gcc `-O0`'s level. fib takes 5× the time of C with Myla's semantics at gcc `-O2`, Ackermann 9×. Arguments are pushed on the stack, the callee loads them from above its frame base and pops them with `ret $8n` ([[MYLA-126]]), and a tail call (`become`, D87) moves them through memory with `push`/`pop` into the caller's argument words. With 16,000 frames deep (Ackermann) that is all memory traffic.

A design round first, part of [[MYLA-160]]'s calling-convention question, since every backend (D117) and the runtime's entry points share the convention:

- [ ] The first arguments and the result in registers (integers and pointers, then floats with [[MYLA-249]]), the rest on the stack; what `become` and the suspended frames of async functions (D90) need from it
- [ ] The cost of the change across the runtime's hand-written entry points (executor, function-value adapters, thunks) against [[MYLA-162]] moving the runtime to Myla
- [ ] Measured on fib, Ackermann and the self-compile

## Measurements and options (2026-11-03, the optimisation pass of [[MYLA-242]])

- **After MYLA-246/249/251:** fib(36) takes 96 ms against 20 ms for C with Myla's semantics at gcc `-O2`, Ackermann(3, 11) 498 ms against 55 ms. That's the same instruction class as gcc `-O0` (fib runs 1.86× gcc `-O2`'s instructions, Ackermann 3.3×).
- **Where it goes**, in fib's code (the first round's disassembly):
  - each argument pushed, then loaded from above the frame base;
  - `ret $8n` popping them;
  - a frame set up and torn down (`push %rbp`, `leave`) even for a leaf;
  - the 32-bit result re-extended (`movslq`) after each operation.

  A tail call (Ackermann) moves its arguments through memory with `push`/`pop` into the caller's argument words.
- **The options:**
  1. **System V for user code:** the first six integer arguments in `%rdi`…`%r9`, floats in `%xmm0`…`%xmm7`, the result in `%rax`/`%xmm0`. The convention C and the platform layer ([[MYLA-162]]) speak, so calls into the runtime and C ([[MYLA-166]]) need no adapters. The caller pops the stack arguments, so `become` with more stack words than the caller has can't reuse the frame ([[MYLA-126]], D87).
  2. **A Myla register convention:** arguments in registers but the callee still popping stack words. That keeps `become` and the suspended frames of async functions (D90) as they are, but adds adapters at every boundary with C.
  3. **Registers for leaf and direct calls only:** a function the compiler sees all calls of (not taken as a value, not `pub`) gets register arguments; everything else keeps today's convention. Least churn, least gain.
- **Recommendation:** option 1 with a rule for `become` (frames sized for the largest tail call, as Rust and Swift do with `musttail`). The adapters option 2 needs cost more over time than the one rule, and every new backend (D117) implements one convention instead of two. The owner decides; the frame-pointer omission for leaves (no `push %rbp` when nothing needs it) can go first, independently.

## Wasm (2026-11-03)

Wasm has no registers or stack a compiler controls: a function has typed parameters and results, and the engine allocates registers. So the registers-or-stack question doesn't arise there, and wasm's C convention (scalars as parameters, structs by pointer into linear memory, a shadow stack for slots whose address is taken) is the natural choice.

Three details follow:
- **A closure's environment** is a hidden IR parameter, mapped per backend: `call_indirect` needs exactly matching signatures, and there is no static-chain register on wasm.
- **`become`** is `return_call` (wasm's tail calls, part of Wasm 3.0), so the stack-word rule doesn't apply there.
- **Several results:** wasm's multiple results could later carry small tuples inside Myla.

FFI on wasm means host imports, which know only numbers, so strings and lists cross as a pointer and a length: the explicit conversions [[MYLA-241]] already proposes.

## Decision: D119 (2026-11-03)

The owner chose option 1, as each target's C convention, with the three details above. The FFI comes later: the benchmarks ([[MYLA-242]]) and the de-risking ([[MYLA-160]]) come first.

Steps, each verified by the bootstrap and the tests:
- [ ] Register arguments and results for every Myla call: direct calls, aggregate results, function values (the environment in `%r10`), tail calls, async frames, the runtime's entry points and adapters, the debug information's parameter locations
- [ ] The checker's rule for `become` with more stack words than the caller received
- [ ] Measured: fib, Ackermann, the self-compile, all benchmarks against the baseline

The frame pointer stays (frame cells, parameters and the debug information are addressed from `%rbp`). Leaving it out of leaf functions would save two instructions per call against a change to every address, so it isn't a first step after all. 16-byte stack alignment at calls matters only for calling C, so it comes with the FFI.
