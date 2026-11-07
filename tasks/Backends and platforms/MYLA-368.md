---
id: MYLA-368
title: "x86-64 code quality in hot loops: spills, inlined frames, value ifs"
type: improvement
status: backlog
priority: low
labels: [codegen, performance, x86-64]
---
Found while tuning `std.digest` ([[MYLA-328]]), whose MD5 runs at 287 MB/s against `md5sum`'s 690. None of these affects correctness:

1. With about 16 values live, x86-64 spills an expression's temporary instead of a long-lived local: the left operand of `(a << 7u32) | (a >> 25u32)` goes to a stack cell, then `or -0x10(%rbp)`. With few live values it stays in a register.
2. An inlined small function keeps its parameters and locals in stack slots: SHA-256's `compress` got a 5.7 KB frame that way, and ran about 25 % slower than the same statements written out. Functions of more than about 8 statements aren't inlined at all.
3. A value `if` (`if n < 10u32 { a } else { b }`) compiles to `setb`, a spill, a compare and a branch, rather than a `cmov` or a direct branch.

The lane's reproductions and generator are in its scratch folder; the first is 16 locals loaded from a list, then a loop over `a = a + m0 + … + m7; a = ((a << 7u32) | (a >> 25u32)) + m8 + … + m15`.

- [ ] Each measured on `std.digest`'s benchmarks and the `benchmarks/` suite before and after
