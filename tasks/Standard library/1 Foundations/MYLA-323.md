---
id: MYLA-323
title: "std.list: building, higher-order operations, sorting, searching"
type: feature
status: review
priority: high
labels: [stdlib, lists, functional, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]], roadmap #16, #17, #18, #19, #22. Methods on `[T]` (`impl<T> [T]`) taking closures. The receiver is a copy, so a method that returns a new list costs a copy only when the list is shared (copy-on-write).

- **Owns:** `lib/std/list.my`, `docs/Language/Standard-library/List.md`
- **Needs:** [[MYLA-319]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] Building: `filled(n, v)` (a function, there being no receiver), `reversed`, `concat`, `extend`, `insert`, `remove_at`, `swap`, `truncate`, `dedup`; `join` on `[str]`
- [x] Higher-order: `map`, `filter`, `fold`, `reduce`, `any`, `all`, `find`, `position`, `count`, `sum`, `min_by`, `max_by`, `flat_map`, `zip`, `enumerate`, `chunks`, `windows`
- [x] Sorting: a stable merge sort as `sort` (`var self`, `T: Ord`), `sort_by(less)`, `sort_by_key`, `sorted`, `is_sorted`; an unstable sort, measured against the stable one
- [x] Searching: `binary_search`, `lower_bound`, `upper_bound`, `partition_point`
- [x] Combinatorics: `permutations`, `combinations`, `next_permutation`
- [x] A sort of 1 million `int`s natively measured, against the AoC `sort.my` and C's `qsort` in `benchmarks/`
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **Built:** [[lib/std/list.my]] and [[Language/Standard-library/List]], with the module's row on [[Language/Standard-library]]. `filled(n, v)` is a function; the rest are methods in `impl<T> [T]`, `impl<T: Eq> [T]` (`contains`, `index_of`, `dedup`), `impl<T: Add> [T]` (`sum`), `impl<T: Ord> [T]` (`sort`, `sorted`, `sort_unstable`, `is_sorted`, `lower_bound`, `upper_bound`, `binary_search`, `next_permutation`) and `impl [str]` (`join`). Beyond the list: `sorted_by(less)`, the copy `sort_by` gives. The unstable sort is `sort_unstable` (Rust's name): an introsort.
- **Names:** none of the task's had to change. `remove`, `contains` and `insert` aren't reserved on lists (D151 reserves `contains` and `remove` on maps only); `remove_at` is the task's name. `sum` takes the zero, `xs.sum(0)`, as a generic `T` has none and a default can't mention a type parameter.
- **Tests first:** the test functions failed before the methods existed (`unknown function 'filled'`, `type '[str]' has no method 'contains'`). Now `build/myla test lib/std/list.my --stdlib lib`: 12/12 passed (two `#test` cases of `join`, ten test functions), and with `--native` 12/12. The heapsort fallback was checked by forcing it (a depth limit of 0): 12/12 both ways, then put back. `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks`: 6 tests OK (`list` is among the modules found).
- **Measured** (1 million `int`s natively, `benchmarks/quicksort`'s numbers; the page has the table): `sort` 125 ms and 918 M instructions, `sort_unstable` 92 ms and 455 M, `sort_by` 150 ms, the quicksort benchmark's `sort` 105 ms and 569 M, the AoC `sort.my` 285 ms, C's `qsort` 110 ms. A merge sort that writes into a second list by index instead of pushing took 13 % fewer instructions and no less time, so `sort` keeps the pushes.
- **Found on the way:**
  - Natively, `assert(cond, msg)` with a message that wasn't a literal failed the IR verifier ("drop of $2 (__temp), which holds no value"); fixed by [[MYLA-355]], which this branch is rebased on, so the tests use `assert` with f-strings.
  - `myla test --native` can't build a `#test` case (still so on `e5195e6`) whose receiver is an empty list: `impl [str] { #test([], "-")[0] fun width(self, sep: str) -> int { … } }` gives a harness with `var __recv = []`, "cannot infer the element type of an empty list". `join`'s empty case is in a test function instead.
  - A lambda's parameter types weren't inferred where the method's function type has a type parameter of its own (`xs.map((x) => x * 2)`: "cannot infer the type of lambda parameter 'x'"); fixed by [[MYLA-356]], so neither the tests nor the page annotate them.
  - Lists have no `==` (`cannot compare values of type '[int32]'`), so the tests compare the lists' text.
