# std.heap

Binary heaps, the priority queues ([[MYLA-330]]). `Heap<T>` holds values of an ordered type and gives the least first, or the greatest; `KeyedHeap<T>` holds values of any type by an `int64` priority, as Dijkstra's algorithm and A* want them. The module imports nothing.

```myla
import std.heap as heap
from std.heap import Heap, KeyedHeap

// The length of the shortest path from node 0 to each node, -1 where none.
fun shortest(edges: [[(int, int64)]]) -> [int64] {
    var dist: [int64] = []
    for i in 0..edges.len() {
        dist.push(-1)
    }
    var todo: KeyedHeap<int> = heap.keyed_new()
    todo.push(0, 0)
    while let Some(e) = todo.pop() {
        let (d, u) = e
        if dist[u] >= 0 {
            continue
        }
        dist[u] = d
        for edge in edges[u] {
            let (v, w) = edge
            if dist[v] < 0 {
                todo.push(d + w, v)
            }
        }
    }
    return dist
}

fun main() {
    var h: Heap<int> = heap.of([5, 1, 4])
    h.push(2)
    print(h.peek().unwrap_or(-1))
    print(h.pop().unwrap_or(-1))
    print(h.into_sorted().map((x) => f"{x}").join(" "))
    let top: Heap<int> = heap.max_of([5, 1, 4, 2])
    print(top.into_sorted().map((x) => f"{x}").join(" "))
    let edges = [[(1, 7i64), (2, 2i64)], [(3, 1i64)], [(1, 3i64)], [], []]
    print(shortest(edges).map((d) => f"{d}").join(" "))
}
// output:
// 1
// 1
// 2 4 5
// 5 4 2 1
// 0 5 2 6 -1
```

| Function | Result |
| --- | --- |
| `new<T: Ord>() -> Heap<T>` | An empty heap that gives the least value first |
| `max_new<T: Ord>() -> Heap<T>` | An empty heap that gives the greatest value first |
| `of<T: Ord>(xs: [T]) -> Heap<T>` | A heap of the elements of `xs`, least first, built in O(n) |
| `max_of<T: Ord>(xs: [T]) -> Heap<T>` | The same, greatest first |
| `keyed_new<T>() -> KeyedHeap<T>` | An empty keyed heap |

| Method of `Heap<T>` | Result |
| --- | --- |
| `h.push(x: T)` | Adds `x`, in O(log n). Needs a `var` place |
| `h.pop() -> Option<T>` | Takes the least element (the greatest, of a max-heap), in O(log n); `None` when the heap is empty. Needs a `var` place |
| `h.peek() -> Option<T>` | The element `pop` would take, left in place |
| `h.len() -> int`, `h.is_empty() -> bool` | The number of elements; whether there are none |
| `h.into_sorted() -> [T]` | The elements in the order `pop` gives them: ascending, or descending for a max-heap; a heapsort, in O(n log n) |
| `h.iter() -> HeapIter<T>` | An iterator over the elements in the order `pop` gives them, lazily: each step pops a copy of the heap, in O(log n), and `h` stays as it is (D171) |

| Method of `KeyedHeap<T>` | Result |
| --- | --- |
| `k.push(priority: int64, value: T)` | Adds `value` with its priority. Needs a `var` place |
| `k.pop() -> Option<(int64, T)>` | Takes a value of the least priority, with its priority. Needs a `var` place |
| `k.peek() -> Option<(int64, T)>` | The entry `pop` would take, left in place |
| `k.len() -> int`, `k.is_empty() -> bool` | The number of entries; whether there are none |

Values of equal priority, or equal values, come out in no set order. A keyed heap gives the least priority first; for the greatest, push `-priority`. `sift_down`, a method of `Heap`, is the heap's own step, which `pop` and `of` take; a program has no need of it. `for x in h.iter()` visits the elements least first (greatest first for a max-heap), and `h.iter() |> iter.take(k)` gives the `k` least in O(n + k log n) without sorting the rest ([[MYLA-425]]): the iterator pops its own copy of the heap, which the first step copies as the heap is shared until then.

A heap's element type comes from where it goes ([[MYLA-315]]): an annotation (`var h: Heap<int> = heap.new()`), a field, a parameter or a return type. With nothing expected, `let h = heap.new()` is an error, "cannot infer type parameter(s) T": annotate the binding. Expecting a `Heap<P>` of a type `P` without `Ord` is an error too, as `T: Ord` is checked against what the expected type fixes. A struct can't carry a bound, so the bound is on the functions and on the methods' `impl`.

## Elements

A `Heap<T>` takes the integers, the floats, `char`, `str` (byte-wise, [[MYLA-318]]) and any type that implements `Ord` (`fun cmp(self, other: Self) -> int`). A `KeyedHeap<T>` holds values of any type by a priority.

## A max-heap

A max-heap is a flag of the heap that `max_new` and `max_of` set, not a `Reverse<T>` wrapper whose `Ord` inverts `cmp`:

- the values go in and come out as they are, with no wrapping and no `.0`;
- every `T: Ord` works, the built-in ones too;
- a generic `impl<T: Ord> Ord for Reverse<T>` didn't link natively when the heap was built (an operator on a generic impl, fixed by [[MYLA-367]]); it works now, but the flag needs no wrapper type.

The flag costs a test per comparison: a million pushes and pops of `int` take 183 ms, against 177 ms for the same heap with the max-heap's code taken out. The comparisons are written out in `push` and `sift_down`; a helper function for them cost 25 %, as the native backend doesn't inline it.

## How it works

A heap is a list in which each element comes before its children, at `2i + 1` and `2i + 2`, so the first element is the one `pop` takes. `push` appends and moves the parents that the new element comes before one level down until its place is found; `pop` takes the first element and does the same from the root with the last one. Both move a hole rather than swap, one write per level. `of` is Floyd's construction: each element that has children is sifted down, the last first, which is O(n) in all. A `KeyedHeap` keeps its priorities and values in two lists side by side, so the comparisons read only `int64`s: faster than one list of `(int64, T)` pairs for small values (242 against 262 ms for a million pushes and pops of `int`) and the same for strings.

## Speed

Measured natively on x86-64, best of five runs, against the `Heap` of the Advent of Code solutions (a keyed heap that swaps; 2026-11-07, `90177ad`):

| Work | Time |
| --- | --- |
| 1 million random `int`s: `push` each, then `pop` until empty, `Heap<int>` | 183 ms |
| The same, a max-heap | 179 ms |
| `of` the million, then `into_sorted` | 177 ms |
| The same million pushes and pops, `KeyedHeap<int>` | 235 ms (Advent of Code's: 293 ms) |
| Dijkstra on a random graph of 100 000 nodes and 1 million edges, `KeyedHeap<int>` | 111 ms (Advent of Code's: 135 ms) |
| The same with a `Heap<Step>`, a struct with its own `cmp` | 169 ms |
