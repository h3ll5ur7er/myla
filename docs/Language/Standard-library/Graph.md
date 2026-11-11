# std.graph

Searches of a graph given by its neighbour function ([[MYLA-342]]): breadth-first and depth-first search, Dijkstra's algorithm, A*, topological sort and connected components. No graph is stored. A search asks `next(u)` for the nodes the edges from `u` lead to, when it reaches `u`, so the graph can be a grid, a puzzle's states or a list of edges, and only the part a search reaches is made. The module imports `std.deque`, `std.heap` and `std.list`.

```myla
import std.graph as graph
import std.grid as grid

fun main() {
    let maze = grid.parse("S.#.....\n.##.##.#\n....#..E").expect("a maze")
    let start = maze.find('S').unwrap_or((0, 0))
    let end = maze.find('E').unwrap_or((0, 0))
    let open = (p: (int, int)) => maze.neighbours4(p).filter((q) => maze.at(q).unwrap_or('#') != '#')

    // Fewest steps, and the way
    let d = graph.bfs(start, open)
    print(f"{d.len()} cells reached, E in {d[end]} steps")
    match graph.bfs_path(start, (p) => p == end, open) {
        Some(path) => {
            var m = maze
            for p in path.nodes[1:path.nodes.len() - 1] {
                m.set(p, 'o')
            }
            print(m.text())
        }
        None => print("no way")
    }

    // Each step costs 1, and 5 more to go up
    let cost = (p: (int, int)) => {
        let (x, y) = p
        return open(p).map((q) => {
            let (qx, qy) = q
            return (q, if qy < y { 6i64 } else { 1i64 })
        })
    }
    let cheap = graph.dijkstra(start, cost)
    print(f"E costs {cheap[end]}")
    let (ex, ey) = end
    let h = (p: (int, int)) => {
        let (x, y) = p
        return ((ex - x).abs() + (ey - y).abs()) as int64
    }
    match graph.astar(start, (p) => p == end, cost, h) {
        Some(path) => print(f"A*: {path.cost} in {path.nodes.len() - 1} steps")
        None => print("no way")
    }

    // Dense nodes: the cells numbered by the grid
    let dense = graph.bfs_dense(maze.cells.len(), maze.index(start), (i) => open(maze.pos(i)).map((q) => maze.index(q)))
    print(dense[maze.index(end)])

    // Order and components
    let deps = (s: str) => match s {
        "shirt" => ["tie", "jacket"]
        "tie" => ["jacket"]
        "trousers" => ["shoes", "jacket"]
        _ => []
    }
    let order = graph.topo_sort(["shirt", "socks", "trousers"], deps).expect("no cycle")
    print(order.join(" "))
    let parts = graph.components([1, 2, 3, 4, 5, 6], (n) => if n % 3 == 0 { [n / 3] } else { [] })
    print(parts.map((c) => c.map((n) => f"{n}").join(",")).join(" "))
}
// output:
// 17 cells reached, E in 13 steps
// S.#oooo.
// o##o##o#
// oooo#.oE
// E costs 23
// A*: 23 in 13 steps
// 13
// shirt socks trousers tie jacket shoes
// 1,3 2,6 4 5
```

| Function | Result |
| --- | --- |
| `bfs<T: Eq + Hash>(start: T, next: (T) -> [T]) -> [T: int]` | The number of edges of a shortest path from `start` to each node it reaches, in the order the search reaches them, `start` first at 0 |
| `bfs_path<T: Eq + Hash>(start: T, goal: (T) -> bool, next: (T) -> [T]) -> Option<Path<T>>` | A path of the fewest edges to a node for which `goal` is true; `start` alone if it is one; `None` if none is reachable |
| `dfs<T: Eq + Hash>(start: T, next: (T) -> [T]) -> [T]` | The nodes reachable from `start` in depth-first preorder, the neighbours in the order `next` gives them |
| `dijkstra<T: Eq + Hash>(start: T, next: (T) -> [(T, int64)]) -> [T: int64]` | The cost of a cheapest path to each node reached, in the order Dijkstra's algorithm settles them, cheapest first |
| `dijkstra_path<T: Eq + Hash>(start: T, goal: (T) -> bool, next: (T) -> [(T, int64)]) -> Option<Path<T>>` | A cheapest path to a goal: Dijkstra's algorithm, stopping at the first goal it settles |
| `astar<T: Eq + Hash>(start: T, goal: (T) -> bool, next: (T) -> [(T, int64)], h: (T) -> int64) -> Option<Path<T>>` | A cheapest path to a goal by A*, `h(u)` the estimate of the cost from `u` to a goal |
| `topo_sort<T: Eq + Hash>(nodes: [T], next: (T) -> [T]) -> Result<[T], GraphError>` | `nodes` and every node their edges reach, each before the nodes its edges lead to; `Err(Cycle)` if there is no such order |
| `components<T: Eq + Hash>(nodes: [T], next: (T) -> [T]) -> [[T]]` | The connected components of `nodes` and every node their edges reach, an edge joining its ends whichever way it points |
| `bfs_dense(n: int, start: int, next: (int) -> [int]) -> [int]` | `bfs` over the nodes 0 to n - 1, a list of distances, -1 where it doesn't reach |
| `dijkstra_dense(n: int, start: int, next: (int) -> [(int, int64)]) -> [int64]` | `dijkstra` over the nodes 0 to n - 1, a list of costs, -1 where it doesn't reach |

| Type | Holds |
| --- | --- |
| `Path<T>` | `nodes: [T]`, from the start to the goal, both included; `cost: int64`, the sum of its edges' weights (the number of edges, for `bfs_path`) |
| `GraphError` | `Cycle`: no topological order exists. It has `message()` and implements `Format` (D168) |

## Nodes and edges

A node is any type a map key can be, `T: Eq + Hash` (D163, D167): an integer, a string, a tuple such as a grid position `(x, y)` or a state `((x, y), dir)`, or a struct that derives both. A weighted edge is a `(node, weight)` pair. A weight is an `int64`: a path's cost is a sum, which can pass the 2³¹ of an `int`, and [[Language/Standard-library/Heap]]'s `KeyedHeap` orders by `int64`. Weights must not be negative: a negative one is a failure in `dijkstra`, `dijkstra_path`, `astar` and `dijkstra_dense` (`dijkstra: edge weight -3 is negative`), where a cycle of negative cost made the search go on for ever ([[MYLA-425]]). A path whose cost passes `int64`'s range is a failure too, and so is a cost plus `h` that does in `astar` (D184).

A goal is a predicate, not a node, so a search can stop at any node that qualifies (`(s) => s.keys == all`), and `(p) => p == end` stops at one.

## The orders

- `bfs` and `dijkstra` return maps in the order they settle the nodes (D105): `d.keys()` lists the nodes by distance.
- `dfs` visits a node's neighbours in the order `next` gives them, as a recursive search does, but with a list for a stack: a chain of 200 000 nodes is no deeper than one.
- `topo_sort` takes, of the nodes that may come next, the one that comes first in `nodes`, then those found through edges in the order they were found. With `nodes` sorted, it gives the least order, as Advent of Code 2018's day 7 asks.
- `components` gives each component's nodes in breadth-first order from its first node, and the components in the order of their first nodes in `nodes`.

## A*

`h(u)` estimates the cost from `u` to the nearest goal. The path found is a cheapest one when `h` never estimates more than the true cost, as the Manhattan distance doesn't on a grid whose steps cost at least 1. A node whose cost improves after it was taken from the heap is taken again, so an `h` that is admissible but not consistent still gives a cheapest path. With `h` always 0, A* is Dijkstra's algorithm; `dijkstra_path` is that.

## Dense nodes

`bfs` and `dijkstra` keep a map keyed by node, which costs a hash and a probe per edge. `bfs_dense` and `dijkstra_dense` take nodes numbered 0 to n - 1 and keep lists instead. On a grid, [[Language/Standard-library/Grid]]'s `index` and `pos` number the cells; a state such as a cell and a direction numbers as `index(p) * 4 + dir`.

## Speed

Measured natively on x86-64, best of five runs, on a 1000×1000 grid:

| Work | Time |
| --- | --- |
| `bfs` over the open grid, nodes `(x, y)`, `next` from `neighbours4` | 426 ms |
| `bfs_dense` over it, `next` through `pos`, `neighbours4` and `index` | 93 ms |
| `bfs_dense` over it, `next` computing the indices | 42 ms |
| `dijkstra` over the grid with weights 1 to 9, nodes `(x, y)` | 1008 ms |
| `dijkstra_dense` over it | 187 ms |
| `dijkstra_path` from one corner to the other | 1069 ms |
| `astar` from one corner to the other, `h` the Manhattan distance | 1046 ms |

The maps keyed by node make `bfs` and `dijkstra` four to ten times slower than the dense searches, so a grid's searches go dense. `astar` with the Manhattan distance saves little on a grid of weights 1 to 9, where it underestimates by far.
