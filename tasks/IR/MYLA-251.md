---
id: MYLA-251
title: "Loop overhead: checks and widening the IR can prove away"
type: improvement
status: backlog
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
