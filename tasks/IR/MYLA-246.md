---
id: MYLA-246
title: Small values copied with moves, not rep movsq
type: improvement
status: done
priority: high
labels: [backend, performance, codegen]
---
Found by the first benchmark round ([[MYLA-242]]). Binary trees ran the same number of instructions as C with Myla's semantics, but took 5.7 times as long. Every match on the three-word `Tree` copied the value into the frame with `cld; rep movsq`. That string instruction is microcoded and starts slowly (tens of cycles even for three words), and callgrind counts it as one instruction.

- [x] The test first: `tests/burn/test_small_copies.py` compiles a match on a small enum, a copy of a three-field struct and one of a nine-word struct. The small copies must have no `rep movsq` in their functions, the big one must keep it, and native and interpreted output must agree. With the compiler before the change, `check` and `small_sum` used `rep movsq`.
- [x] `emit_copy` ([[selfhost/codegen.my]]) copies up to 8 words as `movq` pairs through `%rcx`, which the copy already clobbered, and above that with `rep movsq` as before. Its one caller, the IR's copy instruction, treats `%rcx`, `%rsi` and `%rdi` as clobbered either way.

## Evidence

- Binary trees (depth 18): 5.9 s → 1.9 s, now 1.85× C with Myla's semantics at gcc `-O2` (was 5.7×).
- The self-compile, the real-world program: about 870 ms → 690 ms (median of 7 runs, two rounds), for a 6 % larger compiler (1.63 → 1.73 MB).
- The bootstrap reaches its fixed point; the burn suite passes.
