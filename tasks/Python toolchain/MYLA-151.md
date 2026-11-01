---
id: MYLA-151
title: Map remove with tombstones in the Python backend
type: improvement
status: backlog
priority: low
labels: [python-backend, performance]
---
Split from [[MYLA-16]], whose optional last item it was. The Python backend's map `remove` rebuilds the whole table, O(capacity) per removal ([[src/myla/compiler/codegen_x86.py#L3505]]), where a tombstone (state 2, already reserved) would make it O(1).

- [ ] Removal leaves a tombstone; lookups pass over tombstones, inserts reuse them, growing counts them
- [ ] The map tests and the parity programs with `remove` still pass; a removal-heavy program measured before and after
