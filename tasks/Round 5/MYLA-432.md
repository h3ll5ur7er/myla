---
id: MYLA-432
title: "P18 Check time: IoError on its own, then lazy std modules"
type: improvement
status: todo
priority: medium
labels: [check-time, loader, round-5]
---
Work package P18 of [[Project/Review-2026-11-10]] (wave B). Follows D179.

- [ ] `IoError` and `from_errno` in a small module of their own, so std.io and std.fs no longer import each other (std.io's import reads 36 KB instead of 81 KB; estimated 101 M to about 60 M instructions)
- [ ] One list of the standard functions the back ends name (`std$fmt$…`, `std$slice$…`, `std$task$cancel`), marked as called
- [ ] Then [[MYLA-413]] for the standard library (its prototype miscompiled `slices_and_formats.my` without the list)
- [ ] Then [[MYLA-412]]'s signature cache, toward [[MYLA-359]]'s 5 ms
