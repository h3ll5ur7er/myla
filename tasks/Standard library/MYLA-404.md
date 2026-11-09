---
id: MYLA-404
title: "std.cache: an LRU cache and memoising"
type: feature
status: review
priority: low
labels: [stdlib, collections, cache]
---
Roadmap row #32 ([[Project/Standard-library-roadmap]]).

- [x] `Lru<K, V>` with a capacity: `get` (which refreshes the entry), `put` (which evicts the least recently used), `contains`, `remove`, `len`, `clear`; every operation O(1) on average, over `std.map` and an index-linked list
- [x] Memoising around a map: a `Memo<K, V>` that computes a missing value with a closure and keeps it (and how a recursive function uses it without references)
- [x] Cases interpreted and natively, a measurement of `get`/`put` against a plain map, a page below [[Language/Standard-library]] and the roadmap row

## Proposal (the owner decides)

**A recursive function memoises as a step.** A closure can't call the memo it is in (it captures a copy, which can't change), so `recursive(step)` takes `step(k, known) -> Result<V, K>`: `Ok(v)` when the values it needs are in `known`, else `Err(j)`, a key it needs first; `Memo.get` computes on a stack of its own (a list), so the depth isn't bounded by the call stack (the interpreter's overflows below 20 000 recursive calls; `recursive` went a million deep natively in 486 ms and 10 000 deep in the interpreter's cases). Alternatives: (a) only the pattern any program has, a `var self` method on a struct holding the map, whose recursive calls write the caller's place (twice as fast, 0.99 against 1.91 ms for Fibonacci 10 000 deep natively, but limited by the call stack; the page shows it as the other way); (b) threading the memo through the function, `(Memo, K) -> (Memo, V)`, which every call site has to unpack. Also: `put` returns the evicted entry (`Option<(K, V)>`), which a program may ignore.

## Evidence

- **The API** ([[lib/std/cache.my]], [[Language/Standard-library/Cache]]): `new<K: Eq + Hash, V>(capacity) -> Lru<K, V>`; methods `get(var self, k) -> Option<V>` (refreshes), `put(var self, k, v) -> Option<(K, V)>` (the evicted entry), `peek`, `contains` (neither refreshes), `remove(var self, k) -> Option<V>`, `clear`, `len`, `is_empty`, `capacity`, `keys()` and `items()` most recent first. `new_memo<K, V>(f: (K) -> V) -> Memo<K, V>`, `recursive<K, V>(step: (K, [K: V]) -> Result<V, K>)`; methods `get(var self, k) -> V`, `peek`, `contains`, `set`, `len`, `clear`. A cycle is the failure `std.cache: a step needs a key that needs it (a cycle)`.
- **How:** slots in four lists (key, value, previous, next), a map from key to slot, `head` and `tail`, a free list of removed slots; `get`/`put`/`remove` are one or two map operations and a few index writes. The slots never outnumber the capacity (a case checks it).
- **Cases:** `build/myla test lib/std/cache.my --stdlib lib`: `8/8 passed.` interpreted (1.1 s) and `--native` (eviction order, refresh by `get` and by an update, `peek` without one, removal of the head, tail and last entry with slot reuse, `clear`, capacities 0 and 1, tuple keys and list values, 5000 random gets, puts and removes against a model list with the entries compared after every step, a memo of a function, Fibonacci by `recursive` 90 and 10 000 deep, a cycle's failure). Checked against a broken cache (`get` not refreshing, eviction of the head): 6/8, the eviction case and the model failing (at step 44).
- **Measured** natively on x86-64 with `std.bench` (median of 5, 1 million operations on random keys): `put` with 64k keys, capacity 64k: `[int: int]` 23.0 ms, `Lru` 45.2 ms; `put` with 128k keys into a capacity of 64k (evicting): 124 ms; half `get`, half `put`, each with another `get`, 128k keys: map 68.1 ms, `Lru` 92.4 ms (capacity 64k), 91.5 ms (256k, no eviction). So an `Lru` costs 1.4 to 2 times a map, and an eviction a map removal and insertion more.
- **Docs:** the page with two doc blocks that run (interpreted and natively the same), the row on [[Language/Standard-library]], row #32 on the roadmap, the `myla` skill.
- **Suites** (the branch with all three tasks of the lane): `scripts/bootstrap.sh` reaches the byte-identical fixpoint; `scripts/test.sh fast`: 763 tests, the one failure `test_embedded_std` (`selfhost/embedded_std.my` behind `lib/` until the seed commit); `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks tests.burn.test_lsp tests.burn.test_toml tests.burn.test_compiler_parity tests.burn.test_selfhost_cases tests.burn.test_error_corpus tests.burn.test_selfhost_checker tests.burn.test_project_commands`: `Ran 733 tests in 491.9s OK (skipped=1)`.
