---
id: MYLA-252
title: Faster strings and builders in the runtime
type: improvement
status: backlog
priority: low
labels: [runtime, performance, strings]
---
Found by the benchmarks ([[MYLA-242]]): in the string programs the runtime's routines take most of the time.
- string building: `__str_concat` 25 %, `__str_drop` 15 %, `__alloc` 13 %, `__uint_to_str` 11 %;
- word frequency: `__sb_append_bytes` 24 %.

Myla runs fewer instructions than C with Myla's semantics there (its allocator is cheaper than `malloc`), but takes 1.6× and 2.9× the time.

- [ ] Where the time goes per routine (a byte loop where a block copy would do, growth policy of builders, writing digits)
- [ ] An f-string's pieces formatted straight into one string instead of concatenated pair by pair
- [ ] Measured: string building and word frequency
