---
id: MYLA-162
title: The runtime off assembly - Myla runtime and a platform layer
type: feature
status: backlog
priority: medium
labels: [runtime, llvm, platforms]
---
Third step of [[MYLA-62]]: the runtime (about 3,000 lines of hand-written x86-64 assembly in [[selfhost/codegen.my]]: the allocator with per-worker heaps, strings, maps, builders, printing and float formatting, traps, the work-stealing executor with actor executors, thread state through `%fs`, `clone`, `futex` and raw system calls) rewritten once, as D98 ([[MYLA-160]]) decides, so that new targets only need a thin platform layer. This is the step that makes other platforms affordable.

- [ ] The portable part in Myla (or LLVM IR): allocator, strings, maps, builders, formatting (byte-identical to the interpreter), traps, the executor's logic
- [ ] The platform layer behind a small interface: memory (`mmap`), output and files, processes (`__run`), directories, threads, parking and waking, thread-local state, time, exit; Linux first, with system calls as today
- [ ] Atomics where the runtime needs them (counts of actor handles, queues, the failure flag of D97)
- [ ] Both backends (assembly and LLVM) on x86-64 Linux use it, or the assembly backend keeps its runtime: decided in D98; the gates and the bootstrap still pass, and the cost is measured
