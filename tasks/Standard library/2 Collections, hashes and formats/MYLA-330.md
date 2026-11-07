---
id: MYLA-330
title: "std.set, std.deque, std.heap: the first collections"
type: feature
status: backlog
priority: medium
labels: [stdlib, collections, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #24, #25, #26. Generic collections with constructor functions (`set.new()`, which needs [[MYLA-315]]), on maps that remove in constant time ([[MYLA-310]]). Elements are primitive until [[MYLA-313]] makes tuples and derived structs keys; the set then takes any `Eq + Hash` element unchanged.

- **Owns:** `lib/std/set.my`, `lib/std/deque.my`, `lib/std/heap.my`, `docs/Language/Standard-library/Set.md`, `docs/Language/Standard-library/Deque.md`, `docs/Language/Standard-library/Heap.md`
- **Needs:** [[MYLA-310]], [[MYLA-315]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Set<T>`: `new`, `of(list)`, `insert`, `remove`, `contains`, `len`, `union`, `intersection`, `difference`, `for` over its elements (insertion order)
- [ ] `Deque<T>`: a ring buffer, `push_back`, `push_front`, `pop_back`, `pop_front` (an `Option`), indexing, `len`
- [ ] `Heap<T: Ord>`: `push`, `pop`, `peek`, min-first, and a max-heap by a flag or a wrapper
- [ ] A breadth-first search on a 1000×1000 grid and Dijkstra on a 1 million-edge graph timed natively
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
