---
id: MYLA-342
title: "Algorithms: grid, graph search, bit set, union-find"
type: feature
status: backlog
priority: medium
labels: [stdlib, algorithms, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #28, #29, #30, #31. AoC's toolkit, in std.

- **Owns:** `lib/std/grid.my`, `lib/std/graph.my`, `lib/std/bitset.my`, `lib/std/unionfind.my`, `docs/Language/Standard-library/` (their pages)
- **Needs:** [[MYLA-330]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Grid<T>`: width, height, `at`, `set`, in-bounds, 4 and 8 neighbours, read from text, printed
- [ ] `std.graph`: BFS, DFS, Dijkstra, A*, topological sort, connected components, over a neighbour function
- [ ] `BitSet`: fixed and growable, `popcount`, set operations
- [ ] Union-find with path compression and union by rank
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
