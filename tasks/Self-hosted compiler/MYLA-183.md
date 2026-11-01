---
id: MYLA-183
title: "Frame layout by liveness: slots of disjoint scopes share cells"
type: improvement
status: backlog
priority: medium
labels: [selfhost, ir, performance]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `layout_slots` in [[selfhost/ir_x86.my]] gives every slot its own frame cell: slots of mutually exclusive match arms (`arm_slot`) and of disjoint blocks never overlap, and `Value` is a wide enum, so `Interp.eval` has a 2,576-byte frame, `exec_stmt` 2,224, `eval_name_call` 3,696. That is both the recursion limit of the self-hosted interpreter ([[MYLA-182]]) and the memory-traffic bound [[MYLA-133]] stopped at.

- [ ] Slots of disjoint scopes and match arms share cells (the temporaries already do, `alloc_temps`), measured on the self-compile (time, peak memory, frame sizes of the interpreter's functions)
- [ ] The interpreter's recursion depth before and after
