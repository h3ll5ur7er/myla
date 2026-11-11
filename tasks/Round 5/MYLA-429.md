---
id: MYLA-429
title: "P15 Maps shrink, and iterate in their live size"
type: improvement
status: review
priority: medium
labels: [maps, runtime, performance, round-5]
---
Work package P15 of [[Project/Review-2026-11-09]] (wave B, after [[MYLA-415]]: the same lowering and runtime). Follow-up of [[MYLA-310]].

- [x] M26: a map compacts on remove when most of its slots are dead, so iteration costs its live size (20,000 keys taken oldest-first from a once-10^6 map: 82 s)
- [x] Measured on the map benchmarks before and after

## Evidence

- **As built** ([[lib/std/rt.my]] `map_shrink`, `map_shrink_h`, `map_fit`; [[selfhost/lower.my]] `map_remove`). After `remove` has made the slot a tombstone, counted it out and released its key and value, it compares the count before the removal with the capacity: a map with fewer keys than an eighth of its capacity (`n << 3 < cap`, four instructions on the normal path) calls std.rt's `map_shrink` (`map_shrink_h` for compound keys) on a cold path, which compacts it with `map_rehash` into the capacity an insert's compaction picks (`map_fit`, now one function for the three: the smallest power of two, at least 8, that leaves it at most half full): tombstones dropped, ranks renumbered in order, the new cell stored back through the place. A map of 8 slots never shrinks (a key found means a count of at least 1). After a compaction to `fit(c)` < 4(c + 1) slots, the next comes when fewer than an eighth of those are left, so about an eighth of the capacity has been removed since, which pays for it: a removal stays amortised O(1). Nothing else changes: D105's order (the compaction keeps it, as growth's does), copy-on-write (the removal has made the map unique before; a `for` over the map retains it, so a removal inside the loop works on a copy and the loop walks the keys it began with), the copy, drop and deep copy (whole cells). There is no persistent order array to compact: the ranks are in the slots, and `map_keys`' block of ranks is as long as the next rank, which a compaction resets to the count.
- **Interpreter:** no cliff. Its `MapV` already compacts the holes once they outnumber the entries, rebuilding its index maps, so a walk costs at most twice the live entries: the burn test below at 20,000 keys of which 200 are kept, 10.3 ms against 10.0 ms for a map that never held more (200,000 and 1,000: 77 ms and 78 ms), before the change and after.
- **Test first.** `tests/burn/test_map_remove.py`'s `_SHRINK`: a map grown to n keys and left with its newest k, walked 100 times and then drained oldest-first (`for k in m { first = k; break }`, then `remove`), timed inside the program against a map that only ever held k; the once-big map must take less than three times as long (plus a slack), natively at 200,000 and 1,000 and interpreted at 20,000 and 200. Before: the native test failed, 1,019,581 µs against 4,462 µs (228×); the interpreted one passed. After: both pass, 4.3 ms against 3.6 ms natively. On the other targets before → after (once-big, always-small, µs): aarch64 under qemu 25,329,240 / 143,874 → 143,212 / 128,455; wasm32 under Node 4,386,585 / 32,363 → 32,345 / 27,588.
- **The reproducer** (`review1/repro/native/map_cliff.my`): 200 walks of the one key left of 10^6, 890 ms → 0 ms; 20,000 keys taken oldest-first, 94,448 ms → 2,872 ms. (A map of 20,000 keys that never held more takes 2.8 s the same way: a `for` makes the list of all the keys before its first step, so leaving it at once still costs the live size, [[MYLA-496]].)
- **Parity program** `map_shrinks_on_remove` ([[tests/burn/test_compiler_parity.py]], pinned): 1,000 keys shrunk to six in a scrambled order and the order after new and reinserted keys, a copy taken before keeping all of them, a `for` that removes every key it visits, string keys with list values (pushed to after the compaction), `char` and `int8` keys, a derived struct key and a tuple key (`map_shrink_h`), maps in a struct field and in a list element, and a map emptied and filled again. The same output interpreted and natively, `--checked`, on aarch64 and wasm32, before the change and after (checked by hand against the program).
- **Measured** with callgrind (`benchmarks/run.py word_freq map_remove`, the old compiler built from `bb5380d`'s `selfhost/` against the new; `benchmarks/results/2026-11-11-map-shrink-before.json`, `…-after.json`, [[Development/Benchmarks]]):

  | Myla's instructions | Before | After | Change |
  |---|---:|---:|---:|
  | `word_freq` (100,000), its map only grows | 140.64 M | 140.47 M | −0.1 % |
  | `map_remove` (4,000) | 15.12 M | 15.78 M | +4.4 % (three runs each: 15.13 → 15.58 M, +3 %) |
  | the compiler compiling itself (`stage0` against `stage3`) | 9,340.08 M | 9,340.37 M | +0.003 % |

  The normal path, a removal that doesn't shrink, is four instructions more: `map_remove`'s working set (which never shrinks) 1.68 → 1.76 M instructions in `slide`. The rest of `map_remove`'s increase is its first part, which empties a map of 4,000 keys and now compacts it five times on the way (8,192 slots to 2,048, then 512, 128, 32 and 8): about 0.38 M instructions in `map_rehash`, `map_by_rank`, `map_set_slot` and `zero_bytes`, the price of shrinking; about 0.2 M of the difference is the executor's idle loop (`exec_idle`), which varies by that much between runs of one binary. Times within noise: `word_freq` 901 → 841 ms, `map_remove` 30 → 23 ms (median of 5); the compiler compiling itself 2.32 s → 2.34 s (three runs each).
- **Gates:** the bootstrap's byte-identical fixed point; `scripts/test.sh fast` (839 tests, only `test_embedded_std` failing, as expected before the integrator's seed commit); `test_map_order`, `test_map_remove`, `test_compiler_parity`, `test_std_modules` (interpreted and native), `test_debug_info`, `test_benchmarks`, `test_selfhost_interp`, `test_lsp` (467 tests, OK); on aarch64 and wasm32 `test_map_remove`, `test_compiler_parity`, `test_builtin_impls`, `test_selfhost_codegen`, `test_std_modules`; `myla test` of `lib/std/map.my`, `set.my`, `cache.my` and `hash.my` interpreted, `--native`, on aarch64 and on wasm32; `myla test selfhost/interp.my --native --only map` and `selfhost/lower.my --only map_remove`; and `scripts/test.sh` (1,506 tests, only `test_embedded_std` failing, as above). On aarch64 one run of `test_allocation_does_not_scan_unusable_free_cells` passed its 5 s limit with the machine loaded (load 7 on 4 cores); alone it passes in 2.7 s, and its program (no removals) takes 2.7 s under qemu with the old compiler and the new.

## Proposal (open decision)

When a removal shrinks a map, which no decision settles. Built: **a removal from a map with fewer keys than an eighth of its capacity compacts it** into the capacity growth would pick (at most half full). Alternatives:

- **A quarter instead of an eighth.** A walk would cost at most 4× the live keys rather than 8×, but a compaction to `fit(c)` slots can come two removals after the last (8 keys in 32 slots: the second removal finds 7 < 32/4), so a map hovering there compacts again and again; an eighth always leaves about an eighth of the capacity to remove between two.
- **Compact the gaps only, never the table** (keep the capacity, renumber the ranks): `map_keys`' block of ranks would shrink, but the walk of the slots would still cost the old capacity, which was most of the 94 s.
- **Shrink when walked** (`keys` or `for` compacting a sparse map first): removals pay nothing, but a walk would have to change the map it reads, which a `for` retains and copy-on-write shares.

Recommendation: the eighth, as built.
