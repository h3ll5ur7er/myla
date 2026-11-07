---
id: MYLA-323
title: "std.list: building, higher-order operations, sorting, searching"
type: feature
status: todo
priority: high
labels: [stdlib, lists, functional, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]], roadmap #16, #17, #18, #19, #22. Methods on `[T]` (`impl<T> [T]`) taking closures. The receiver is a copy, so a method that returns a new list costs a copy only when the list is shared (copy-on-write).

- **Owns:** `lib/std/list.my`, `docs/Language/Standard-library/List.md`
- **Needs:** [[MYLA-319]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] Building: `filled(n, v)` (a function, there being no receiver), `reversed`, `concat`, `extend`, `insert`, `remove_at`, `swap`, `truncate`, `dedup`; `join` on `[str]`
- [ ] Higher-order: `map`, `filter`, `fold`, `reduce`, `any`, `all`, `find`, `position`, `count`, `sum`, `min_by`, `max_by`, `flat_map`, `zip`, `enumerate`, `chunks`, `windows`
- [ ] Sorting: a stable merge sort as `sort` (`var self`, `T: Ord`), `sort_by(less)`, `sort_by_key`, `sorted`, `is_sorted`; an unstable sort, measured against the stable one
- [ ] Searching: `binary_search`, `lower_bound`, `upper_bound`, `partition_point`
- [ ] Combinatorics: `permutations`, `combinations`, `next_permutation`
- [ ] A sort of 1 million `int`s natively measured, against the AoC `sort.my` and C's `qsort` in `benchmarks/`
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
