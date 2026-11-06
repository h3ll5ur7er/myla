---
id: MYLA-251
title: "Loop overhead: checks and widening the IR can prove away"
type: improvement
status: in-progress
priority: medium
labels: [backend, performance, optimisation, ir]
---
Found by the benchmarks ([[MYLA-242]]), the optimisations D117 (3) plans. In the loops of the sieve, Game of Life and fannkuch, each list write repeats work that holds for the whole loop:
- loading the list from its frame slot;
- the copy-on-write check (is the list held once?);
- the bounds check;
- an address computation through a temporary.

Each 32-bit operation is sign-extended again (`movslq`), and `!flag` goes through `sete`/`movzbq` before its test. The sieve runs 2.1× the instructions of C with Myla's semantics at gcc `-O2`, Game of Life 1.9×. LLVM wouldn't remove the copy-on-write checks either: only Myla's IR knows the rule.

- [x] A list held in a register across a loop; the copy-on-write check once, before the loop, when nothing in the loop shares the list (2026-11-06)
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

## The copy-on-write check before the loop (2026-11-06)

- **What.** An IR pass, [[selfhost/hoist.my]] (`hoist_cows`, after inlining and before the verifier, so on every target): in a loop that calls nothing and uses a list's slot only to read its elements and length and to write them through `cow`, the `cow` of that slot goes into the block the loop is entered from (after what there touches the slot, so a comparison stays next to its branch), and what read each `cow` in the loop reads its result. Inner loops first, then outwards again. A loop is the blocks from one a jump goes back to up to that jump in the emitted order, entered at its first block from one block; anything else (a call, a store to the slot, an append, pop, retain or copy of the list) leaves it alone. After the first turn the list is held once, and nothing in such a loop can share it again, so the check every turn found it so; one moved before a loop that runs no turn copies a shared list nobody writes, which no program sees. The list's pointer stays in a register across the loop too.
- **Test first.** `test_loop_overhead.test_the_copy_on_write_check_is_made_before_the_loop`: the sieve's inner loop (`composite[j] = true`) calls no `__clone_list`, which the compiler before fails. `test_copies_on_write_around_loops_print_the_same`: a list shared before the loop is still copied once; one shared again in the loop (`olds.push(ys)`, `keep = zs`) or replaced (`ws = [...]`) keeps its check; the same output natively and interpreted. `scripts/test-target.py` passes on aarch64 and wasm32.
- **Measured** (callgrind at each benchmark's profile size, wall time the median of 7 runs twice; built with the compiler of the commit before):
  - sieve 131.6 → 114.2 million instructions (−13 %), its inner loop 11 instructions instead of 16; time within noise;
  - fannkuch 33.2 → 29.6 million (−11 %), 434 → 355 ms (about 1.2× as fast);
  - quicksort 93.6 → 91.9 million (−2 %), time within noise; Game of Life unchanged (its loops call functions);
  - the self-compile (the same input, the commit before's sources) takes 1.1 % more instructions, the pass's own cost after making it cheap: no work for a function without `cow` or a loop that calls anything, the slots of addresses computed once a round, the renaming only in the loop.
