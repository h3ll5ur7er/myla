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

