---
id: MYLA-343
title: "std.btree: a sorted map and set"
type: feature
status: done
priority: low
labels: [stdlib, collections, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #27. A B-tree keyed by `Ord`: ordered iteration, range queries, `first`, `last`, `floor`, `ceiling`. Value semantics make every update copy a path; measure it against the hash map.

- **Owns:** `lib/std/btree.my`, `docs/Language/Standard-library/Btree.md`
- **Needs:** [[MYLA-315]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `SortedMap<K: Ord, V>` and `SortedSet<T: Ord>`
- [x] 1 million inserts and lookups timed natively, against the hash map
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **Design.** A B+ tree in an arena: the nodes are a `[Node<K, V>]` list, a node's keys, values and children each a list of its own, children named by index, freed slots reused; linked leaves; top-down insert (split a full child before entering it) and remove (fill a child at the minimum from a sibling or by a merge before entering it). `ORDER` 64. `SortedSet<T>` is the same tree with `()` values; `union`, `intersection` and `difference` merge the sorted elements and build the tree level by level in O(n + m). [[lib/std/btree.my]], [[Language/Standard-library/Btree]].
- **Tests:** 8 test functions (all the functions are generic, D116), 8/8 interpreted (15 s), with `--native`, `--target aarch64-linux` and `--target wasm32-wasi` (node). `against_a_model` makes 4000 random inserts and removes against a model and checks the invariants after each step (keys in order and inside their node's range, every node but the root at least half full, every leaf at the same depth, the leaf links in order, the count, no slot lost) and every query (`get`, `contains`, `floor`, `ceiling`, `range`); `deep_tree` fills a three-level tree with 8000 random keys and empties it by `pop_first`, `pop_last` and `remove`. Mutations (a separator not updated after a borrow from the right leaf, after a borrow from the left leaf or inner node, after a borrow from the right inner node) each fail them. After a bootstrap, `tests.burn.test_std_modules` and `tests.burn.test_doc_blocks` pass (6 tests).
- **Speed**, natively, best of five, 1 million random `int` keys: `SortedMap<int, int>` insert 369 ms, get 253 ms, remove 502 ms, 1 million `range` of about 10 keys 421 ms; `[int: int]` 148, 34 and 32 ms. `SortedSet<int>` insert 345 ms, contains 243 ms; std.set's `Set<int>` 132 and 26 ms.
- **Layouts measured** (1 million inserts and gets of `int`): this arena 335 and 246 ms; a nested recursive enum copying its path 1636 and 283 ms; a flat arena with every node's keys in one list 284 and 193 ms (left out: its free slots would keep copies of removed keys and values alive). `ORDER` 32 to 128 measured, 64 chosen.
- **Found:** a division by the constant 2 compiles to `idiv` natively: `(lo + hi) / 2` in the search cost a fifth of a lookup against `>> 1`.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
