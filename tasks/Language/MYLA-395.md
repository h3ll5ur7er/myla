---
id: MYLA-395
title: "Integer overflow traps in the interpreter, under myla test and in --checked builds (D175)"
type: feature
status: todo
priority: medium
labels: [language, integers, overflow, interpreter, codegen]
---
The implementation of D175 ([[MYLA-311]]). After the toolchain-fixes batches ([[Project/Follow-up-plan]]), since it touches the interpreter and the lowering they change. Its own pull request, with its seed (D156).

- [ ] Find every place `selfhost/`, `lib/std/` and `tools/` wrap on purpose (hashes: `std.hash`'s wyhash and FNV, `std.digest`, `std.random`'s xoshiro and SplitMix, `std.num`, `std.rt`'s allocator and maps, the compiler's own hashing) and move them to `std.int`'s `wrapping_add`/`wrapping_sub`/`wrapping_mul` (natively these must stay one instruction: check the lowering inlines them). A first pass with the checks on, running every suite, finds the rest
- [ ] The interpreter: `+`, `-`, `*`, unary `-` on integers check their width and fail with `integer overflow` (a runtime error with its position, as `index out of bounds`); decide `<<` and `/` of the minimum by -1 and record it on D175
- [ ] Native code: a `--checked` build (and `myla test --native`, which builds its harness checked) adds the check after each such operation (`jo`/`jc` on x86-64, the flags on aarch64, a compare on wasm32); a plain `myla build` is unchanged, measured (the benchmarks' code size and time)
- [ ] Constant folding and literals: an overflowing constant expression is a compile-time error where it is one today, a trap otherwise
- [ ] Parity programs on every target, interpreted and `--checked`, and the error corpus
- [ ] [[Language/Types]] or [[Language/Expressions-and-operators]] (D4's paragraph), [[Language/Standard-library/Int]], the `myla` skill
