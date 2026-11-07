---
id: MYLA-271
title: "Map remove without rebuilding the whole table"
type: improvement
status: review
priority: low
labels: [runtime, performance, maps]
---
Replaces [[MYLA-151]], which named the retired Python backend. A map's `remove` makes the key's slot a tombstone, then rebuilds the whole table (`__map_rebuild` in `std.rt`) to keep the insertion order's ranks without gaps (D105, [[MYLA-179]]). Every remove is O(capacity). It is lowered as IR since [[MYLA-163]], so a fix lands on every target.

- [x] Tombstones kept until a grow or a threshold, the ranks renumbered lazily (or an order list beside the table), so a remove is O(1) amortized; the iteration order unchanged (D105); measured on a program that removes many keys

## Comments

- 2026-11-07, Claude: resolved by [[MYLA-310]], which the Advent of Code findings asked for ([[Project/AoC-2015-2021]], F1). A remove now leaves the tombstone and a gap in the ranks without rebuilding. The next rank to give out lives in a word after the slots. `keys()` and `for` skip the gaps. An insert compacts the table (tombstones dropped, ranks renumbered, the capacity chosen to leave it at most half full) once the ranks given out reach 3/4 of the capacity. D105's order is unchanged. Measured: removing 32,000 keys natively went from 15,337 ms to 0.55 ms, and the `benchmarks/map_remove` results are in `benchmarks/results/2026-11-07-map-remove-*.json`. `__map_rebuild` is no longer called; `std.rt`'s `map_rebuild` stays as a no-op until the next seed, as the seed's lowering still names it. Moved to review for the owner to close.
