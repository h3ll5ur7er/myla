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


## Splitting, first try: saved around calls (2026-11-03, set aside)

A value with no register for all its life, whose only obstacle was the calls it crosses, got a caller-saved register saved into its frame cell before each such call and loaded after, when the stores and loads (weighted by their blocks) cost less than its own reads and writes. On the compiler's own code it made things 0.36% worse (0.05% with the saves at most a third of the uses), and estimating the cost cost the compiler 76 million instructions: such a value holds its register for all its life, which later values would have used better, and the compiler's loops seldom have a cold call that this pays around. Splitting that helps will have to shorten the value's register life itself (a register between the calls, the frame across them), with the moves at block edges; not tried yet.

## Splitting, second try: pieces between calls (2026-11-03, set aside)

A value left without a register that crosses calls (7.6% of the compiler's loop-weighted value uses, 2,109 values) was cut at each clobbering position it is live across into pieces; each piece took a free caller-saved register when its reads and writes outweighed the store before the cut and the load after it; emission stored and loaded around the cuts, set each split value's place at every block start, and moved it on the edges where two pieces meet (a trampoline on a conditional branch, so the other successor's registers are untouched). Correct (the bootstrap's fixed point, every example; the first build found that a temporary reading a split slot must not alias its home), but the compiler's own code took 2.3% more instructions on the same source and the pass cost the compiler 262 million instructions. The cost model left out the edges' moves: a value used once a loop turn and crossing a call pays a store, a load and a move on the back edge every turn, where the frame cost it a memory operand. With splitting, `--ssa` came within 0.2% of the normal form.

What a splitting that pays needs: the edges' moves in the cost (a piece's register chosen with its neighbours', or one register across a loop when the call is on its cold path), the cuts only where the value is read between two calls, and a cheaper pass (here it walked every register's holders for every piece). Not pursued further for now.
