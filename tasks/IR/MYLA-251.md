---
id: MYLA-251
title: "Loop overhead: checks and widening the IR can prove away"
type: improvement
status: done
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
- [x] Bounds checks dropped where the index is provably in range (a counting loop below `len`), others merged (merging finds next to nothing, below)
- [x] Re-extension only where a value's upper bits are read; a negated condition branching directly (the extensions left are read whole next, below)
- [x] Measured: the sieve, Game of Life, fannkuch, quicksort, and the self-compile

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

## A counting loop's step without the re-extension (2026-11-06)

- **What.** An IR pass, [[selfhost/ranges.my]] (`widen_counters`, after `hoist_cows`): an int32 `+ 1` of a slot that `i < x` (an int32 `x`) guards, the slot not stored since, can't overflow, so it is retyped int64, which every backend does without its wrap (`movslq`, `sxtw`, `i64.extend32_s`). A forward analysis over the blocks per int32 slot whose address nothing takes: the true side of `cmp < int32 (load $i), x` (or `x > i`) knows it, a store ends it, a block knows what all its predecessors do. That covers `for i in 0..n` and `while i < n { … i += 1 }`. A `<=` loop's step, a second step in the same turn, any step but 1 and any counter without such a comparison keep the wrap.
- **Test first.** `test_loop_overhead.test_a_counting_loops_increment_is_not_re_extended` (the step of `for i in 0..n` has no `movslq` after its `addq $1`) failed before; `test_counting_loops_at_the_limit_print_the_same` runs loops at `INT32_MAX` (a `<` loop ending there, a `<=` loop that must wrap, two steps a turn that must wrap) natively and interpreted, and `test_aarch64`/`test_wasm` run the same program on both targets.
- **Measured** (callgrind, against the commit before): sieve 114.2 → 110.2 million instructions (−3.5 %), fannkuch 29.6 → 28.9 (−2.1 %), Game of Life 155.9 → 153.6 (−1.5 %), quicksort −0.2 %; the self-compile (the same input) 0.9 % more instructions, the pass's cost after it skips functions without a loop and without a slot both compared and stepped, its wall time within noise.

## Bounds checks a counting loop proves (2026-11-06)

- **What.** `elem` has a flag: `unchecked` where the lowering knows the index is below the length, and no backend compares them ([[docs/Architecture/IR.md]], "Bounds checks"). The lowering ([[selfhost/lower.my]]) marks two kinds. A `for` loop's element: the loop holds the list and tests the index against its length every turn. And `xs[i]` or `xs[i] = v` in `for i in a..b`: `a` not negative (a constant that isn't, an enclosing range's variable from such a start, or either plus 0 or 1, which can't wrap below an integer end), `b` the length of what `xs` names, `xs.len()` or a `let n = xs.len()` before the loop, and that length unchanged while the loop runs. It is unchanged for a fixed variable or a part of one (a `let`, a parameter other than `var self`, a capture), and for a `var` the function never resizes or replaces: `resized_in_block` scans the body for a variable assigned whole, the receiver of any method but `len`, or the first argument of `push`, `pop`, `remove` or `append`; writing an element (`bs[i].vx -= …`) is no resize. Facts are kept by slot, so a `let xs` shadowing the list inside the loop is another list, and a `len` of the program's own on a list type (D144) isn't the length.
- **Test first.** `test_native_runtime.test_a_counting_loop_below_a_length_indexes_unchecked` reads the IR of five functions (a sum below `xs.len()`, n_body's pairs below `let n = bodies.len()` from `i + 1`, a `var` copy whose fields are written, a string's bytes, a `for x in xs`); the compiler before marks none of their eight accesses. `test_a_counting_loop_keeps_the_checks_it_needs`: nine loops that must still trap where they did (the list reassigned after `let n = xs.len()`, shadowed in the body, popped in the body or in an enclosing loop, another list indexed, a negative start, `i + 2`, a field of a `var` struct, a string reassigned), at the same position. The first fails on the compiler before; the second passes there too, and guards the proof.
- **Measured** (callgrind, x86-64, against ba41033): n_body 86.5 → 71.8 million instructions (−17.0 %), closures 137.6 → 127.1 (−7.6 %: `for` loops over lists), string_build 91.6 → 88.7 (−3.2 %), quicksort −0.2 %; the rest unchanged, every output the same; the self-compile 5,123.6 → 5,100.2 million (−0.46 %). The benchmarks the item was written for (sieve, Game of Life, fannkuch) index with `j += i`, `(y + n - 1) % n` or `r - 1` against lengths earlier loops set, which this doesn't follow.

## Re-extension where it can matter (2026-11-06)

- **Where they are.** Sign extensions are 4–8 % of the instructions the loop benchmarks execute (callgrind with `--dump-instr`: sieve 4.4 %, Game of Life 4.1 %, quicksort 5.5 %, fannkuch 7.7 %, a third of fannkuch's and two fifths of quicksort's being sign-extending loads, which cost what a plain load does). The hot ones mostly extend a value that is an index next: the sieve's `j += i` (its 4.3 million), quicksort's and fannkuch's loop counters. An int32 temporary kept with its upper half undefined, extended only where it is read whole, would move those to the index's use, not remove them; removing them needs ranges, as `widen_counters` has for `+ 1`.
- **What went.** In x86-64's code generation ([[selfhost/codegen.my]] `emit_int_op`, [[selfhost/ir_x86.my]]), no wrap after an operation whose result can't leave its operands' range, the operands being extended already: a remainder, a quotient but a signed one by a variable (the minimum by −1 wraps), `&`, `|`, `^` and `>>`, by a variable or a constant. And `emit` drops `movslq %Rd, %R` when the instruction after it writes `%Rd` without reading memory through `%R` (`extension_overwritten`; `ext_at` remembers the line, so the check costs the other lines two byte compares; one into another register, which a folded load leaves, stays): a 32-bit write clears the upper half, and its low bits don't depend on the upper half of what it reads, as in `(y + n - 1) % n`'s `leal`s. aarch64's and wasm32's extensions stay as they are.
- **Test first.** `test_loop_overhead.test_a_remainder_and_a_sum_before_it_are_not_re_extended` (no `movslq` after `idivq`'s remainder or before a `leal` overwriting it) failed before; `test_integer_operations_at_the_limits_print_the_same` runs every such operation on int32, uint32, int8, uint8 and int16 values at their limits, by variables and by constants (`a ^ 4294967295u32`, `b & -2147483648`), the minimum divided by −1, natively and interpreted (239 lines, the same).
- **Measured** (callgrind, against fa6b457): closures 127.1 → 125.1 million instructions (−1.6 %), Game of Life −0.8 %, quicksort −0.3 %, string_build −0.2 %, fannkuch −0.1 %, the rest unchanged; the self-compile 5,100.2 → 5,107.3 million (+0.14 %), the check's own cost, as the compiler's integer code gains little (it was +0.8 % while `emit` looked at every line's text).

## What is left

- **Bounds checks.** Of the benchmark loops, n_body's index below a length (above); the others' indices are `j += i`, `r - 1`, `(y + n - 1) % n` against lengths that earlier `push` loops set, so dropping their checks needs the lists' lengths followed across loops (that `perm` holds `n` elements), a larger analysis than the item assumed. Merging repeated checks finds next to nothing: counting `elem` instructions of the same list and index in one block over quicksort, fannkuch, sieve and Game of Life gives 1 of 59 (a read sees the list through `load`, a write through `cow`).
- **Re-extension in general** (only where a value's upper bits are read) is a different representation of int32 temporaries in each backend; measured above, it would move the hot extensions rather than remove them. Removing those needs ranges (that `j + i` can't overflow), like `widen_counters`'s for `+ 1`. aarch64's and wasm32's extensions after a remainder or a bitwise operation could go the way x86-64's did.
