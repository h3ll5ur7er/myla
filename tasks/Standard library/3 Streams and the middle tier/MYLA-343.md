---
id: MYLA-343
title: "std.btree: a sorted map and set"
type: feature
status: backlog
priority: low
labels: [stdlib, collections, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #27. A B-tree keyed by `Ord`: ordered iteration, range queries, `first`, `last`, `floor`, `ceiling`. Value semantics make every update copy a path; measure it against the hash map.

- **Owns:** `lib/std/btree.my`, `docs/Language/Standard-library/Btree.md`
- **Needs:** [[MYLA-315]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `SortedMap<K: Ord, V>` and `SortedSet<T: Ord>`
- [ ] 1 million inserts and lookups timed natively, against the hash map
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
