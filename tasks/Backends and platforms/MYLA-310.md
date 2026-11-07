---
id: MYLA-310
title: "Maps: remove in constant time, natively and in the interpreter"
type: bug
status: review
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

- [x] A benchmark (`benchmarks/`, [[Development/Benchmarks]]) that inserts and removes at scale, and its baseline before the fix
- [x] Native: tombstones without a rebuild, ranks with gaps, compaction on growth; every target (x86-64, aarch64, wasm32)
- [x] Interpreter: map lookup and remove not linear in the map's size
- [x] D105's order still holds: the map tests and the parity programs unchanged

## Evidence

- **Native, as built** ([[lib/std/rt.my]] maps, [[selfhost/lower.my]] `map_remove`). The cell gains one word after its slots, the next rank. A new key takes it; `remove` makes the slot a tombstone, counts it out and releases its key and value, and calls nothing: its rank stays a gap. `map_keys` (which `for k in m` uses) writes each key at its rank when there are no gaps, as before, and otherwise goes through a block of the slots by rank, skipping the gaps. The next rank counts every slot a key has filled since the last compaction, tombstones included, so `map_put_slot` compacts when it reaches 3/4 of the capacity: tombstones dropped, ranks renumbered in order, the capacity the smallest power of two that leaves the map at most half full. A map that only grows grows exactly as before; one with removals stays the same size or shrinks. A probe still always ends at an empty slot, and each compaction is paid for by the quarter of the capacity filled since the last, so every operation is amortised O(1). `map_rebuild` stays in std.rt as a no-op, for code compiled by the seed's lowering, which still calls it (the bootstrap's stage 1); the new compiler doesn't call it, and it can go after the next seed. The copy-on-write clone, the deep copy between tasks and the drop already copy or walk whole cells and occupied slots, so they needed no change; the gdb pretty-printer sorts by rank and shows a map with gaps in order.
- **Interpreter, as built** ([[selfhost/interp.my]] `MapV`). `Value.VMap` holds a `MapV`: the keys and values as parallel lists in insertion order, a hole where a key was removed (`here` false), and an index from key to place, a native `[int64: int32]` for integer, `char` and `bool` keys (by number, as `value_eq` compares them) and a `[str: int32]` for strings; another kind of key, which the language has none of yet, falls back to a search of the entries. Removal makes a hole and drops the key from the index; the holes are compacted away once they outnumber the entries. Lookups, `contains`, `m[k] = v` and the map step of a place were linear searches and are now index lookups. Order, printing and equality are unchanged, except a parity fix: a map literal that gives a key twice kept both entries in the interpreter (`[1: "a", 2: "b", 1: "c"]` had 3); it now keeps the first place and the last value, as native code always did.
- **Tests first.** `tests/burn/test_map_remove.py` (added to the target suites, [[tests/burn/_targets.py]]): a program of 30,000 mixed inserts, replacements, removals and reinsertions over 700 keys, copies going their own way, a map emptied and filled again, gaps carried through growth, string keys and the repeated literal key, against Python's dict in both runners; and removal timed at n and 4n keys, which must take less than 8× (plus a slack for a loaded machine), natively at 5,003 keys and interpreted at 1,999. Before: the order test passed (the order was right, only slow) and both timing tests failed, 4× the keys taking 19× the time natively (253 ms → 4,778 ms) and 24.5× interpreted (64 ms → 1,579 ms). After: all three pass, on x86-64, aarch64 and wasm32.
- **Measured** (removal only, the keys inserted first; the working set inserts a key and removes the oldest, 128,000 steps):

  | | Native before | Native after | `myla run` before | `myla run` after |
  |---|---:|---:|---:|---:|
  | remove 4,000 keys | 156 ms | 0.05 ms | 269 ms | 19 ms |
  | remove 8,000 keys | 682 ms | 0.10 ms | 2,020 ms | 42 ms |
  | remove 16,000 keys | 3,494 ms | 0.21 ms | 13,634 ms | 82 ms |
  | remove 32,000 keys | 15,337 ms | 0.55 ms | 67,407 ms | 161 ms |
  | working set of 1,000 | 1,476 ms | 9.4 ms | 5,800 ms | 1,000 ms |

- **The benchmark** `benchmarks/map_remove` (32,000 keys, then the working set over 128,000): 16,248 ms → 15 ms natively, 4,361 M → 14.9 M instructions at 4,000; C takes 5 ms, C with Myla's semantics 7 ms (`benchmarks/results/2026-11-07-map-remove-before.json`, `…-after.json`). Word frequency, whose map only grows: the same native time (603 and 605 ms, the median of 9 interleaved runs, 0.6 % more instructions), 3× as fast interpreted (8.3 s → 2.8 s at 100,000 words).
- **Gates:** the bootstrap's byte-identical fixed point; `test_map_order`, `test_map_remove`, `test_std_modules`, `test_json`, `test_toml`, `test_builtin_methods`, `test_unit_programs`, `test_debug_info`, `test_benchmarks`, `test_selfhost_interp`, `test_compiler_parity`, `test_examples_run`; `myla test` of `selfhost/interp.my` (interpreted, and `--native` for the map cases) and `selfhost/repl.my`; on aarch64 and wasm32, `test_map_remove`, `test_compiler_parity`, `test_builtin_impls`, `test_selfhost_codegen` and `test_examples_compile`; and `scripts/test.sh fast`.
- [[MYLA-271]] (backlog) asked for the same native fix and is done by this one.
