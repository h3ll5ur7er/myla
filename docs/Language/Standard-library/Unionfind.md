# std.unionfind

`UnionFind`, disjoint sets of the integers 0 to n - 1 ([[MYLA-342]]). It joins two sets and tells whether two integers are in the same one, in nearly constant time each. The module imports nothing.

```myla
import std.unionfind as unionfind

fun main() {
    // Kruskal's algorithm: the cheapest edges that join every node
    var edges = [(4, 0, 1), (8, 1, 2), (2, 2, 3), (6, 0, 2), (3, 3, 4), (5, 1, 3), (7, 4, 5), (9, 3, 5)]
    edges.sort_by((a, b) => a.0 < b.0)
    var u = unionfind.new(6)
    var total = 0
    for e in edges {
        let (w, a, b) = e
        if u.union(a, b) {
            total += w
        }
    }
    print(f"{total} for {u.sets()} set")

    var v = unionfind.new(7)
    v.union(0, 4)
    v.union(5, 2)
    v.union(4, 6)
    print(v.same(0, 6))
    print(v.size_of(6))
    print(v.groups().map((g) => g.map((i) => f"{i}").join(",")).join(" "))
    let x = v.add()
    print(f"{x}: {v.sets()} sets of {v.len()}")
}
// output:
// 21 for 1 set
// true
// 3
// 0,4,6 1 2,5 3
// 7: 5 sets of 8
```

| Function | Result |
| --- | --- |
| `new(n: int) -> UnionFind` | The integers 0 to n - 1, each in a set of its own |

| Method | Result |
| --- | --- |
| `u.find(x: int) -> int` | The root of `x`'s set, which stands for the set: two integers are in the same set when `find` gives the same root |
| `u.union(a: int, b: int) -> bool` | Joins the sets of `a` and `b`; true if they were two |
| `u.same(a: int, b: int) -> bool` | Whether `a` and `b` are in the same set |
| `u.size_of(x: int) -> int` | The number of integers in `x`'s set |
| `u.groups() -> [[int]]` | The sets, each ascending, in the order of their least integers |
| `u.add() -> int` | Adds an integer in a set of its own: `len()` before the call |
| `u.len() -> int` | The number of integers |
| `u.sets() -> int` | The number of sets |

Every method but `len` and `sets` needs a `var` place (see below). An integer outside 0 to `len() - 1` is a failure that names the method and the integer, `unionfind.find: element 3 is out of range for 3 elements`, and `new` of a negative number is one too (D184, [[MYLA-550]]; they were a list's index error).

## How it works

The sets are a forest: each integer points at a parent, a root at itself, and the root stands for its tree's set. `find` follows the parents to the root, then points every integer it passed straight at the root (path compression). `union` hangs the root of the lower tree under the root of the other (union by rank, a rank being an upper bound of a tree's height). With both, any run of m operations on n integers takes O(m α(n)) time, α the inverse of Ackermann's function, below 5 for any n that fits in memory.

`find` changes the forest, so it takes `var self`, and so do `union`, `same`, `size_of` and `groups`, which call it. A union-find is a value: a copy has its own forest, and its compressed paths are part of it.

The integers are what the sets hold. Other values are numbered first, with a `[T: int]` map from each to its number; [[Language/Standard-library/Graph]]'s `components` does that for the nodes of a graph.

## Speed

Measured natively on x86-64, best of five runs: `new(1000000)`, a million `union`s of random pairs, then a `find` of each integer: 82 ms (2026-11-08, `38c1555`).
