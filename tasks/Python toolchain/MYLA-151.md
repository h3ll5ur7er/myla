---
id: MYLA-151
title: Map remove with tombstones in the Python backend
type: improvement
status: done
priority: low
labels: [python-backend, performance]
---
Split from [[MYLA-16]], whose optional last item it was. The Python backend's map `remove` rebuilds the whole table, O(capacity) per removal (`src/myla/compiler/codegen_x86.py#L3505` (removed with the Python toolchain, D101)), where a tombstone (state 2, already reserved) would make it O(1).

- [ ] Removal leaves a tombstone; lookups pass over tombstones, inserts reuse them, growing counts them (superseded by [[MYLA-271]]: the Python backend went, and std.rt's maps leave tombstones)
- [ ] The map tests and the parity programs with `remove` still pass; a removal-heavy program measured before and after (superseded by [[MYLA-271]]: the Python backend went, and std.rt's maps leave tombstones)

Superseded by [[MYLA-271]] (2026-11-04): the Python backend is gone and maps are std.rt's, lowered as IR on every target. Closing this one is the owner's call.

Superseded by [[MYLA-271]]; closed with the owner's agreement (2026-11-05).
