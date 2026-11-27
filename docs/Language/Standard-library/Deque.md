# std.deque

`Deque<T>`, a double-ended queue ([[MYLA-330]]): it adds and takes elements at both ends in constant time, and reaches any element by its index in constant time. It is the queue too: `push_back` and `pop_front` are a queue's push and pop, and `push_back` and `pop_back` a stack's. The module imports nothing.

```myla
import std.deque as deque
from std.deque import Deque

// The order in which a breadth-first search from 0 reaches the nodes.
fun bfs(edges: [[int]]) -> [int] {
    var seen: [bool] = []
    for i in 0..edges.len() {
        seen.push(false)
    }
    var order: [int] = []
    var todo: Deque<int> = deque.new()
    todo.push_back(0)
    seen[0] = true
    while let Some(u) = todo.pop_front() {
        order.push(u)
        for v in edges[u] {
            if !seen[v] {
                seen[v] = true
                todo.push_back(v)
            }
        }
    }
    return order
}

fun main() {
    print(bfs([[1, 2], [3], [3, 4], [], [0]]).map((u) => f"{u}").join(" "))
    var d: Deque<str> = deque.of(["b", "c"])
    d.push_front("a")
    d.push_back("d")
    d.set(1, "B")
    print(d.get(1).unwrap_or("-"))
    print(d.get(9).unwrap_or("-"))
    print(f"{d.items().join(",")} {d.len()}")
    print(d.pop_back().unwrap_or("-"))
    print(d.front().unwrap_or("-"))
}
// output:
// 0 1 2 3 4
// B
// -
// a,B,c,d 4
// d
// a
```

| Function | Result |
| --- | --- |
| `new<T>() -> Deque<T>` | An empty deque |
| `with_capacity<T>(n: int) -> Deque<T>` | An empty deque whose first push makes room for `n` elements, so that it doesn't grow again before it holds more. A negative `n` or one past 2^30 (1073741824, the most elements a deque holds) is a runtime error naming it (D184) |
| `of<T>(xs: [T]) -> Deque<T>` | The elements of `xs`, `xs[0]` at the front |

| Method | Result |
| --- | --- |
| `d.push_back(v: T)`, `d.push_front(v: T)` | Adds `v` at the back, at the front. Needs a `var` place |
| `d.pop_back() -> Option<T>`, `d.pop_front() -> Option<T>` | Takes the element at the back, at the front; `None` when the deque is empty. Needs a `var` place |
| `d.back() -> Option<T>`, `d.front() -> Option<T>` | The element at the back, at the front, left in place |
| `d.get(i: int) -> Option<T>` | The element `i` places from the front (0 is the front); `None` for an `i` out of bounds |
| `d.set(i: int, v: T)` | Sets the element `i` places from the front to `v`. An `i` out of bounds is a failure, as it is for a list. Needs a `var` place |
| `d.len() -> int`, `d.is_empty() -> bool` | The number of elements; whether there are none |
| `d.items() -> [T]` | The elements, front to back |
| `d.iter() -> DequeIter<T>` | An iterator over the elements, front to back (D171) |

A deque's element type comes from where it goes ([[MYLA-315]]): an annotation (`var q: Deque<int> = deque.new()`), a field, a parameter or a return type. With nothing expected, `let d = deque.new()` is an error, "cannot infer type parameter(s) T": annotate the binding. `for x in d.iter()` visits the elements front to back without making a list, and `d.iter()` starts a pipeline of [[Language/Standard-library/Iter]] (D171, [[MYLA-425]]); the iterator holds the deque as it was when `iter()` was called, and a copy of it keeps its own position. A deque holds at most 2^30 elements, the most slots a power of two in an `int` gives: a push past them is a runtime error. `grow`, a method of `Deque`, is the deque's own step, which a push takes when every slot is taken; a program has no need of it.

## How it works

A deque is a ring buffer: a list of slots whose length is a power of two, the slot of the front element and the number of elements. The element `i` places from the front is in the slot `(head + i) & (slots - 1)`, so the elements can wrap around the end of the list. When every slot is taken, the next push doubles the slots, in amortized constant time.

A generic `T` has no value to fill an empty slot with, so the slots of a new buffer hold copies of the first element pushed, and a doubling appends a copy of the slots as they are, which also puts the elements that wrapped around after the others again. A slot keeps its value until it is written again: what a deque holds on to is bounded by its slots, as what a list holds is by its capacity. The first growth makes 4 slots, or the power of two that `with_capacity(n)` asks for.

A ring buffer was measured against two stacks (a reversed list for the front, a list for the back, half of one moved to the other when it runs out): the stacks were faster at filling a deque with a million elements and emptying it (8 against 11 ms, best of five), the ring buffer at the steady traffic of a search, where elements come and go (a million pops and pushes with a thousand in the queue: 4 against 6 ms, with strings 7 against 11 ms). The ring buffer also reaches an element by index without a branch, and a search is what a deque is for.

## Speed

Measured natively on x86-64, best of five runs (2026-11-07, `90177ad`):

| Work | Time |
| --- | --- |
| 1 million `push_back`, then `pop_front` until empty | 7 ms |
| 1 million `push_front`, then `pop_front` until empty | 6 ms |
| The list and head index that Advent of Code solutions used as a queue, the same work | 6 ms |
| Breadth-first search of a 1000×1000 grid with a `[bool]` per cell | 19 ms (the Advent of Code queue: 19 ms) |
