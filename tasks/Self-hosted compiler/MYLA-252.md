---
id: MYLA-252
title: Faster strings and builders in the runtime
type: improvement
status: review
priority: low
labels: [runtime, performance, strings]
---
Found by the benchmarks ([[MYLA-242]]): in the string programs the runtime's routines take most of the time.
- string building: `__str_concat` 25 %, `__str_drop` 15 %, `__alloc` 13 %, `__uint_to_str` 11 %;
- word frequency: `__sb_append_bytes` 24 %.

Myla runs fewer instructions than C with Myla's semantics there (its allocator is cheaper than `malloc`), but takes 1.6× and 2.9× the time.

- [x] Where the time goes per routine (a byte loop where a block copy would do, growth policy of builders, writing digits)
- [ ] An f-string's pieces formatted straight into one string instead of concatenated pair by pair
- [x] Measured: string building and word frequency

## Evidence

- **Where the time went:** every byte copy of the runtime was `cld; rep movsb`, a microcoded instruction whose start costs tens of cycles: the same trap as [[MYLA-246]]'s `rep movsq`, for strings of a few bytes. callgrind counts it as one instruction, which is why the string programs ran fewer instructions than C but took longer.
- **The fix:** `emit_byte_copy` copies 8 bytes at a time, then the tail, and keeps `rep movsb` for copies of 512 bytes and up, where it is fast. It is used in concatenation, number formatting, both copies of a builder's append, the list clone (a copy-on-write copy) and the builder clone. The deep copies and the list and map growth copy large blocks and keep `rep movsb`.
- **The test first:** `tests/burn/test_byte_copies.py` covers concatenation, builders (with ranges), f-strings, number formatting up to `u64::MAX` and list clones, for lengths 0–40 and across 512. The output must be the same natively and interpreted, and `__str_concat` must have the short path, which the compiler before the change lacks.
- **Measured** against the baseline ([[Development/Benchmarks]]):
  - string building 528 → 320 ms (1.65× as fast), now faster than C with Myla's semantics (0.86× its time);
  - word frequency 952 → 621 ms (1.53× as fast), now 1.9× C with Myla's semantics (was 2.9×).
  - Their instruction counts rose (the loop's instructions were one `rep movsb` before), and the time fell.
- **Left for later:** an f-string's pieces are still formatted and concatenated pair by pair; with string building already ahead of C, it is no longer what limits it.
- The bootstrap reaches its fixed point; the burn suite passes (896 tests).
