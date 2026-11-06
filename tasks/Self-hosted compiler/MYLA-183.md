---
id: MYLA-183
title: "Frame layout: slots of disjoint scopes share cells"
type: improvement
status: review
priority: medium
labels: [selfhost, ir, performance]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `layout_slots` in [[selfhost/ir_x86.my]] gives every slot its own frame cell: slots of mutually exclusive match arms (`arm_slot`) and of disjoint blocks never overlap, and `Value` is a wide enum, so `Interp.eval` has a 2,576-byte frame, `exec_stmt` 2,224, `eval_name_call` 3,696. That is both the recursion limit of the self-hosted interpreter ([[MYLA-182]]) and the memory-traffic bound [[MYLA-133]] stopped at.

- [x] Slots of disjoint scopes and match arms share cells (the temporaries already do, `alloc_temps`), measured on the self-compile (time, frame sizes of the interpreter's functions)
- [x] The interpreter's recursion depth before and after

Decided by D112 ([[MYLA-210]]): by scope; a liveness analysis only if the measurements after this still show a need.

## Evidence

- The lowering numbers the scopes it opens (blocks, match arms) in `IrFunc.scope_parent` and gives each local the scope it is declared in (`Slot.scope`, set by `declare_as`; a slot declared in two scopes, and every temporary, keeps a cell of its own, since a statement's temporaries can outlive a nested scope: `f(match a {…}, match b {…})`). `slot_positions` in [[selfhost/ir_x86.my]] places the slots that aren't an inner scope's locals one after the other, then each scope's locals after those of the scopes around it, so sibling scopes share cells; stack frames and async heap frames use it.
- Measured on `build/myla` (the CLI, with the interpreter) before and after: all frames 691,408 → 605,424 bytes (1,546 functions, −12 %); `Interp.eval` 2,576 → 1,568 bytes, `Interp.exec_stmt` 2,224 → 960, `Interp.eval_name_call` 4,288 → 3,760. The interpreter's recursion in the 120 MiB main stack (a build without `MAX_CALL_DEPTH`, bisected on `down(n)`): about 9,125 → 12,773 calls (+40 %). `MAX_CALL_DEPTH` stays 2,500, a margin for functions that take more stack per call. A self-compile takes the same time (1.02 s before, 1.04 s after).
- The burn suite (836 tests) passes and the bootstrap reaches its fixed point (6,233,228 bytes) with the new seed.

## Reopened (2026-11-06)

**Reopened by [[Project/Review-2026-11]] (R18).** `let`s in an `if`/`else` pair take four cells (two 64-byte `let`s in each branch: a 272-byte frame) while match arms share (128 bytes). `declare_as` and `slot_positions` look right, so either `if` blocks get scope 0 or something else is in the frame.

- [x] Find why the `if`/`else` scopes don't share, fix or document; a frame-size test for the `if` case

Not reproduced: the `if` branches share. Two 64-byte `let`s in each branch of an `if`/`else`, of an `else if` chain of three and of a two-arm `match` give the same 144-byte frame (two cells and the saved registers; a cell per `let` would be 256 and 384 bytes). The other shapes tried all share as well: an `if` as a value, branch `let`s of tuples, of a parameter's copy, of a list element, `var`s in place of `let`s, and an `async fun`'s heap frame (176 bytes with one `let` per branch or with both). The 272 bytes of the review most likely came from something other than the branch locals, a statement's temporaries for example, which keep cells of their own (above). `test_the_branches_of_an_if_share_frame_cells` in `tests/burn/test_selfhost_codegen.py` holds the three shapes below 192 bytes and the `if` equal to the `match`.
