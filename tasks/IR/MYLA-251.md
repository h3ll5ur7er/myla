---
id: MYLA-251
title: "Loop overhead: checks and widening the IR can prove away"
type: improvement
status: todo
priority: medium
labels: [backend, performance, optimisation, ir]
---
Found by the benchmarks ([[MYLA-242]]), the optimisations D117 (3) plans. In the loops of the sieve, Game of Life and fannkuch, each list write repeats work that holds for the whole loop:
- loading the list from its frame slot;
- the copy-on-write check (is the list held once?);
- the bounds check;
- an address computation through a temporary.

Each 32-bit operation is sign-extended again (`movslq`), and `!flag` goes through `sete`/`movzbq` before its test. The sieve runs 2.1× the instructions of C with Myla's semantics at gcc `-O2`, Game of Life 1.9×. LLVM wouldn't remove the copy-on-write checks either: only Myla's IR knows the rule.

- [ ] A list held in a register across a loop; the copy-on-write check once, before the loop, when nothing in the loop shares the list
- [ ] Bounds checks dropped where the index is provably in range (a counting loop below `len`), others merged
- [ ] Re-extension only where a value's upper bits are read; a negated condition branching directly
- [ ] Measured: the sieve, Game of Life, fannkuch, quicksort, and the self-compile

## Done so far (2026-11-03, the optimisation pass of [[MYLA-242]])

Three peepholes from the list above; the analyses (hoisting the copy-on-write check, proving bounds, fewer re-extensions) are still to do.

- A `!` that only a branch reads is the inverted jump: the sieve's `!composite[i]` no longer goes through `sete`/`movzbq`.
- The last block falls into the epilogue instead of jumping to the next line.
- A copy-on-write check takes the list's address straight into `%rcx`.
- `tests/burn/test_loop_overhead.py`: the compiler before the change fails its two code checks; programs that branch on negated flags print the same natively and interpreted.
- Measured against the baseline: sieve 1.07× as fast, fib, fannkuch and Game of Life within noise (1–3 % fewer instructions). The compiler's own assembly is 1 % smaller.

## From the new targets (2026-11-04)

These are passes on the IR ([[selfhost/ssa.my]], [[selfhost/inline.my]] are the models), not x86-64 instruction selection, so aarch64 and wasm gain from them too; only the re-extension item is per backend.
