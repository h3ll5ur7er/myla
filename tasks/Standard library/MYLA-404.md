---
id: MYLA-404
title: "std.cache: an LRU cache and memoising"
type: feature
status: todo
priority: low
labels: [stdlib, collections, cache]
---
Roadmap row #32 ([[Project/Standard-library-roadmap]]).

- [ ] `Lru<K, V>` with a capacity: `get` (which refreshes the entry), `put` (which evicts the least recently used), `contains`, `remove`, `len`, `clear`; every operation O(1) on average, over `std.map` and an index-linked list
- [ ] Memoising around a map: a `Memo<K, V>` that computes a missing value with a closure and keeps it (and how a recursive function uses it without references)
- [ ] Cases interpreted and natively, a measurement of `get`/`put` against a plain map, a page below [[Language/Standard-library]] and the roadmap row
