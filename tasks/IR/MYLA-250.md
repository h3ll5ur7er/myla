---
id: MYLA-250
title: Arguments and results in registers
type: design
status: backlog
priority: medium
labels: [backend, performance, calling-convention]
---
Found by the benchmarks ([[MYLA-242]]): call-heavy code runs at gcc `-O0`'s level. fib takes 5× the time of C with Myla's semantics at gcc `-O2`, Ackermann 9×. Arguments are pushed on the stack, the callee loads them from above its frame base and pops them with `ret $8n` ([[MYLA-126]]), and a tail call (`become`, D87) moves them through memory with `push`/`pop` into the caller's argument words. With 16,000 frames deep (Ackermann) that is all memory traffic.

A design round first, part of [[MYLA-160]]'s calling-convention question, since every backend (D117) and the runtime's entry points share the convention:

- [ ] The first arguments and the result in registers (integers and pointers, then floats with [[MYLA-249]]), the rest on the stack; what `become` and the suspended frames of async functions (D90) need from it
- [ ] The cost of the change across the runtime's hand-written entry points (executor, function-value adapters, thunks) against [[MYLA-162]] moving the runtime to Myla
- [ ] Measured on fib, Ackermann and the self-compile
