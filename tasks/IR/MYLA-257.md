---
id: MYLA-257
title: "Register allocation on lifetime intervals with holes (D123's backend half)"
type: feature
status: in-progress
priority: medium
labels: [backend, ir, performance]
---
The backend half of D123 ([[MYLA-254]]), and what the runtime's remaining hot routines wait for ([[MYLA-162]], "Where the backend stops the port"). Today's allocator (`alloc_regs` in [[selfhost/ir_x86.my]]) gives each value one interval, from its first to its last position in emission order, and keeps it out of the caller-saved registers when any call lies inside. So a value read after a cold block that calls something counts that call as crossing it, a loop variable's join value and its next value always interfere, and the SSA prototype (`--ssa`) costs the compiler 2.9% more instructions where it should save.

The way, after Wimmer and Franz ("Linear Scan Register Allocation on SSA Form", CGO 2010), in steps each measured on the self-compile and the benchmarks:

- [x] **Lifetime intervals with holes:** each value's ranges from block liveness and a backward walk of each block; interference and the calls inside a value's life tested on the ranges, the scan keeping active and inactive intervals. Values and policy otherwise as today.
- [x] **Move hints:** a copy's source and destination (the SSA join copies, a parameter into its home) prefer one register, so the copy disappears.
- [ ] **SSA by default** once it is a gain with the above (`--ssa` today).
- [ ] **Splitting:** a value that has no register for all its life gets one for part of it, spilled and reloaded around the calls it crosses, the moves at block edges resolved.
- [ ] Then the hot routines: the string builder's append (done, cheaper than the assembly), map insertion and growth, list growth ([[MYLA-162]]).

Measured tools: `tests/burn/test_selfhost_codegen.py` for the forms, the instruction counts of the self-compile (the same compiler source built by the old and new backend, run on the same input, to separate the code's quality from the compiler's own work) and of the benchmarks.

## Step 1: lifetimes with holes, move hints (2026-11-03)

- **Ranges:** position p is the points 2p (its reads) and 2p + 1 (its writes); each value's ranges come from the blocks' live-out sets (`live_spans`) and a backward walk of each block (`live_ranges`), merged where they touch. A call at p clobbers a value holding both of p's points, or the read point when it doesn't read its operands first (`range_clobbers`, `callpos`).
- **The scan** (`alloc_regs`): values by their first point; per register a list of holders (`hfirst`, `hnext`), each with a cursor at its first range not over (`hcur`), those done unlinked as they are met; the first free register in the order of preference (the other side of a copy, a call's own argument register, caller-saved, callee-saved), else the one whose holders in the way weigh least if less than the value. A function value read after a call's arguments keeps out of the argument registers.
- **With it:** a load from a variable's register into a temporary's is one move or none, and a value held back in `%rax` that has a register and another reader is stored there at once, by the instruction that computed it, so readers take it from there (`reg_of`).
- **Measured** (instructions): the benchmarks 2.75% fewer on the geometric mean (Ackermann 22%, closures 4.3%, string building 1.3%, binary trees 0.9%, fannkuch 1%; none more); the compiler built by it 1.5% fewer on the same source; the allocator's own work as much again, so the self-compile is where it was. Making it cheap took: linked holder lists instead of lists rebuilt at each point (it first cost the compiler 5%), a cursor per holder, one comparison against a value in one range, stopping at the first free register, and `live_spans` no longer computing the intervals the ranges replace.
- **SSA** (`--ssa`) is still 2.3% behind the normal form with it (was 2.9%): its loops (the allocator itself, the map lookup) lose to the variables' registers; splitting, and the join copies' coalescing, come next.

