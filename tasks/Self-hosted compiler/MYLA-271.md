---
id: MYLA-271
title: "Map remove without rebuilding the whole table"
type: improvement
status: backlog
priority: low
labels: [runtime, performance, maps]
---
Replaces [[MYLA-151]], which named the retired Python backend. A map's `remove` makes the key's slot a tombstone, then rebuilds the whole table (`__map_rebuild` in `std.rt`) to keep the insertion order's ranks without gaps (D105, [[MYLA-179]]). Every remove is O(capacity). It is lowered as IR since [[MYLA-163]], so a fix lands on every target.

- [ ] Tombstones kept until a grow or a threshold, the ranks renumbered lazily (or an order list beside the table), so a remove is O(1) amortized; the iteration order unchanged (D105); measured on a program that removes many keys
