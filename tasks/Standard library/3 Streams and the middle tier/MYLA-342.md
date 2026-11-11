---
id: MYLA-342
title: "Algorithms: grid, graph search, bit set, union-find"
type: feature
status: done
priority: medium
labels: [stdlib, algorithms, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #28, #29, #30, #31. AoC's toolkit, in std.

- **Owns:** `lib/std/grid.my`, `lib/std/graph.my`, `lib/std/bitset.my`, `lib/std/unionfind.my`, `docs/Language/Standard-library/` (their pages)
- **Needs:** [[MYLA-330]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Grid<T>`: width, height, `at`, `set`, in-bounds, 4 and 8 neighbours, read from text, printed
- [x] `std.graph`: BFS, DFS, Dijkstra, A*, topological sort, connected components, over a neighbour function
- [x] `BitSet`: fixed and growable, `popcount`, set operations
- [x] Union-find with path compression and union by rank
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **Modules and pages:** [[lib/std/grid.my]], [[lib/std/graph.my]], [[lib/std/bitset.my]], [[lib/std/unionfind.my]]; [[Language/Standard-library/Grid]], [[Language/Standard-library/Graph]], [[Language/Standard-library/Bitset]], [[Language/Standard-library/Unionfind]], four rows of the index on [[Language/Standard-library]].
- **Choices:**
  - A grid position is an `(int, int)` tuple, not a `#derive(Eq, Hash)` struct `Pos`: it needs no import to write or take apart, and is the node `std.graph` wants. Measured, natively, a generic BFS over a 1000×1000 grid keyed by each: tuples 461 to 477 ms, the struct 465 to 504 ms, an `int` 373 to 380 ms.
  - `std.graph` works over a neighbour function, `(T) -> [T]` or `(T) -> [(T, int64)]`. Weights are `int64`, as `KeyedHeap`'s priorities are and as path costs need. Goals are predicates. Paths are `Option<Path<T>>` with `nodes` and `cost`; distances are maps in settle order. `bfs_dense` and `dijkstra_dense` over numbered nodes keep lists: four to ten times faster than the maps on a grid, so `Grid` has `index` and `pos`.
  - `astar` reopens a node whose cost improves, so an admissible but inconsistent `h` still gives a cheapest path; `dijkstra_path` is `astar` with `h` 0. `topo_sort` takes the earliest available node in `nodes`' order (a `KeyedHeap` of node numbers), so sorted nodes give the least order (AoC 2018 day 7's example `CABDFE` is a test). `components` treats edges as undirected.
  - `BitSet` keeps one form per set (a growable set has no zero word at its end; a fixed set has exactly its words), so `#derive(Eq, Hash)` is right and a `BitSet` is a map key. A written `Hash` that skipped zero words would need `std.hash`'s `Hasher` methods, and importing `std.hash` breaks the native harness (MYLA-360, below). `complemented` is for fixed sets only. `popcount` is a SWAR popcount, as Myla has no `count_ones` yet.
  - `UnionFind` is over `0..n` with `add()` to grow; `find`, `union`, `same`, `size_of`, `groups` take `var self`, as `find` compresses.
- **Tests first:** every public function was written as a `panic("todo")` stub over its cases: unionfind 0/15, bitset 0/60 (before the redesign to one form), grid 0/14, graph 0/9 passed. Now, with `--stdlib lib`: unionfind 15/15, bitset 73/73 (67 since [[MYLA-376]] and [[MYLA-396]] moved its bit counts to std.int), grid 13/13, graph 9/9, interpreted and with `--native`; on `--target aarch64-linux` (qemu) 15/15, 73/73, 10/10 (before the three `new_cells` cases), 9/9. On `--target wasm32-wasi` (Node) unionfind 15/15 and graph 9/9; bitset and grid stop at their first panic-expecting case (MYLA-370), and their other cases pass with `--only` (bitset 12/12 of `a`, grid 6/6 of `i`). After `scripts/bootstrap.sh`, `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks`: `Ran 6 tests … OK`.
- **Measurements**, natively on x86-64, best of five runs, on a machine shared with other lanes:
  - BFS over a 1000×1000 open grid: `graph.bfs` with `(x, y)` nodes and `neighbours4` 426 ms; `bfs_dense` through `pos`/`neighbours4`/`index` 93 ms; `bfs_dense` computing indices 42 ms.
  - Dijkstra over a 1000×1000 grid of weights 1 to 9: `graph.dijkstra` 1008 ms, `dijkstra_dense` 187 ms; `dijkstra_path` corner to corner 1069 ms, `astar` with the Manhattan distance 1046 ms.
  - `UnionFind`: `new(1000000)`, a million random unions, a find of each: 82 ms.
  - `BitSet`: a sieve to 10 million 107 ms (a `[bool]` 81 ms); 100 unions and intersections with popcounts of two million-bit sets 11 ms.
- **Bugs found** (worked around, not fixed here):
  1. The native test harness can't compare an enum of one variant: `__myla_eq_*` always adds `_ => { return false }`, which is an unreachable arm when the enum has one variant ([[selfhost/harness.my]], the line that appends the variant's arm). A `#test(1)[E.Only(1)]` on `fun f(x: int) -> E` with `enum E { Only(int) }` passes interpreted; `--native` fails with "unreachable match arm (a previous arm already matches everything)". `GridError` has one variant, so `parse`'s cases are a test function.
  2. A generic `impl<T: Format> Format for Box<T>` doesn't link natively when used by `print(b)` or `f"{b}"` ("undefined reference to `myla_Box.format`"); the interpreter prints it. Calling `b.format("")` links. The `Format` case of [[MYLA-367]]. So `Grid` has `text()`, not `Format`.
  3. [[MYLA-360]] also holds for `std.hash`: a `lib/std` module importing it runs `std.hash`'s cases as its own, and its native harness doesn't build ("unexpected character '`'"). The `Hasher` methods aren't reachable from a `std` module without that import.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-425]]: `row`/`column` out of range behave differently; negative weights unchecked.
