---
id: MYLA-310
title: "Maps: remove in constant time, natively and in the interpreter"
type: bug
status: todo
priority: high
labels: [maps, performance, runtime, interpreter]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F1). `m.remove(k)` takes time in the map's size, so a map used as a working set gets quadratic. 2017 Day 22 did not finish in minutes. It finished in 0.22 s once the solution stored a "gone" value instead of removing keys.

## Cause

- **Native:** `map_remove` in [[selfhost/lower.my]] makes the entry a tombstone and then calls `__map_rebuild` ([[lib/std/rt.my]] `map_rebuild`, i.e. `map_rehash` at the same capacity). The rebuild walks every slot, drops the tombstone and moves each later insertion rank down by one, which keeps the ranks dense for `for k in m` and `keys()` (D105, [[MYLA-179]]). So each remove costs O(capacity).
- **Interpreter:** a map is two lists, keys and values ([[selfhost/interp.my]] `Value.VMap`). `map_remove` copies both without the key (`map_without`), and a lookup is a linear `key_index`. So every map operation in `myla run` is O(n), not only remove.

## Evidence (master `d5d80bc`)

Removing every key of an `[int64: int]`, inserted 0 to n-1 (the best of two native runs, one interpreted run):

| Keys | Native | `myla run` |
| --- | --- | --- |
| 4,000 | 164 ms | 306 ms |
| 8,000 | 672 ms | 2,048 ms |
| 16,000 | 3,211 ms | 13,555 ms |

## Suggested fix

- **Native:** leave the tombstone in its slot, so probes go past it, and don't renumber the ranks: ranks only grow, with gaps where keys were removed. `keys()` and `for` go through the ranks and skip the gaps. The table is compacted, with tombstones dropped and ranks renumbered, when it grows or when tombstones plus live keys pass the load factor. That makes remove amortised O(1), and D105's order is unchanged.
- **Interpreter:** an index from key to position beside the two lists (or the native map's layout), with removal by tombstone and compaction as above.

- [ ] A benchmark (`benchmarks/`, [[Development/Benchmarks]]) that inserts and removes at scale, and its baseline before the fix
- [ ] Native: tombstones without a rebuild, ranks with gaps, compaction on growth; every target (x86-64, aarch64, wasm32)
- [ ] Interpreter: map lookup and remove not linear in the map's size
- [ ] D105's order still holds: the map tests and the parity programs unchanged
