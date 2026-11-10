---
id: MYLA-330
title: "std.set, std.deque, std.heap: the first collections"
type: feature
status: done
priority: medium
labels: [stdlib, collections, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #24, #25, #26. Generic collections with constructor functions (`set.new()`, which needs [[MYLA-315]]), on maps that remove in constant time ([[MYLA-310]]). Elements are primitive until [[MYLA-313]] makes tuples and derived structs keys; the set then takes any `Eq + Hash` element unchanged.

- **Owns:** `lib/std/set.my`, `lib/std/deque.my`, `lib/std/heap.my`, `docs/Language/Standard-library/Set.md`, `docs/Language/Standard-library/Deque.md`, `docs/Language/Standard-library/Heap.md`
- **Needs:** [[MYLA-310]], [[MYLA-315]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Set<T>`: `new`, `of(list)`, `insert`, `remove`, `contains`, `len`, `union`, `intersection`, `difference`, `for` over its elements (insertion order)
- [x] `Deque<T>`: a ring buffer, `push_back`, `push_front`, `pop_back`, `pop_front` (an `Option`), indexing, `len`
- [x] `Heap<T: Ord>`: `push`, `pop`, `peek`, min-first, and a max-heap by a flag or a wrapper
- [x] A breadth-first search on a 1000×1000 grid and Dijkstra on a 1 million-edge graph timed natively
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **The API.**
  - [[lib/std/set.my]], [[Language/Standard-library/Set]]: `new<T>() -> Set<T>`, `of<T>(xs: [T]) -> Set<T>`; methods `insert(var self, x) -> bool`, `remove(var self, x) -> bool`, `contains(x) -> bool`, `len() -> int`, `is_empty() -> bool`, `items() -> [T]`, `union(other) -> Set<T>`, `intersection(other)`, `difference(other)`, `is_subset(other) -> bool`. A `Set<T>` is a `[T: ()]` map (the unit type works as a value), with no bound on `T`, so MYLA-313's keys need no change here. `for x in s` needs an iterator trait ([[MYLA-353]]); the page says to write `for x in s.items()`.
  - [[lib/std/deque.my]], [[Language/Standard-library/Deque]]: `new<T>()`, `with_capacity<T>(n)`, `of<T>(xs)`; methods `push_back(v)`, `push_front(v)`, `pop_back() -> Option<T>`, `pop_front() -> Option<T>`, `front()`, `back()`, `get(i) -> Option<T>`, `set(var self, i, v)` (out of bounds: a failure, as for a list), `len()`, `is_empty()`, `items() -> [T]`. A ring buffer of a power of two slots with a head index and a count; growth doubles by appending a copy of the slots, which unwraps the elements in place (a generic `T` has no filler value, so slots hold copies).
  - [[lib/std/heap.my]], [[Language/Standard-library/Heap]]: `new<T: Ord>()`, `max_new<T: Ord>()`, `of<T: Ord>(xs)` and `max_of<T: Ord>(xs)` (Floyd's O(n)); methods `push(x)`, `pop() -> Option<T>`, `peek() -> Option<T>`, `len()`, `is_empty()`, `into_sorted() -> [T]` (pop's order, an in-place heapsort). `keyed_new<T>() -> KeyedHeap<T>`; methods `push(priority: int64, value: T)`, `pop() -> Option<(int64, T)>`, `peek()`, `len()`, `is_empty()`.
  - Visible helper methods, as methods inside an `impl` can't be private: `Heap.sift_down(i, n)` and `Deque.grow(v)`; both pages say a program has no need of them.
- **Max-heap: a flag**, not a `Reverse<T>` wrapper: the values go in and out unwrapped, every `T: Ord` works, and a wrapper doesn't link natively (bug 1 below). Its cost, best of five, a million `int` pushes and pops: 183 ms against 177 ms with the max-heap's code taken out. The comparisons are written out in `push` and `sift_down`: a `before(a, b, max)` helper cost 214 ms.
- **Tests first.** The test functions were written over stubs (`unreachable()`): `deque.my` 0/6, `heap.my` 0/6 passed; `set.my`'s, written with the code, fail on a deliberately broken `insert` (3/4). Now, with `--stdlib lib`, interpreted, `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node, `MYLA_EMULATOR="node tools/wasm/run.mjs"`): set 4/4, deque 6/6, heap 7/7 on each. Every public function is generic, which a `#test` case can't take (D116), so all are test functions with `assert` (D162): models for the deque (a list, wrap-around, growth from both ends) and the heap (a sorted list, pushes and pops interleaved; heapify of 0 to 1001 random elements checked by order and by tally), `int64`, `float`, `char` and a struct with its own `cmp`. After `scripts/bootstrap.sh`, `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks`: `Ran 6 tests … OK` (the three doc blocks print the same interpreted and natively).
- **Measurements**, natively on x86-64, best of five, against the Advent of Code helpers (`Queue`, a list and a head index; `Heap`, a keyed heap that swaps):
  - BFS over a 1000×1000 grid (about a quarter walls): `Deque` + `Set<int>` 156 ms, `Deque` + a bare `[int: ()]` 141 ms, `Deque` + `[bool]` 19 ms, the AoC `Queue` + `[bool]` 19 ms.
  - Dijkstra over a random graph of 100 000 nodes and 1 000 000 edges: `KeyedHeap<int>` 111 ms, the AoC `Heap` 135 ms, `Heap<Step>` (a struct with its own `cmp`) 169 ms.
  - A million: `Set` insert then remove 148 ms (a bare map 153 ms); `Deque` `push_back`/`pop_front` 7 ms, `push_front`/`pop_front` 6 ms, the AoC `Queue` 6 ms; `Heap<int>` push then pop 183 ms, max-heap 179 ms, `of` + `into_sorted` 177 ms; `KeyedHeap<int>` 235 ms, the AoC `Heap` 293 ms.
  - The choices measured: a ring buffer against two stacks (fill and drain a million: 11 against 8 ms; steady queue traffic: 4 against 6 ms, with strings 7 against 11 ms); the keyed heap's two lists against one list of `(int64, T)` (242 against 262 ms for `int`, the same for `str`).
- **Compiler bugs found** (worked around, not fixed here):
  1. An operator on a generic struct whose trait impl is generic doesn't link natively: it calls the unmonomorphized method. The interpreter prints `true`; `build` fails with `undefined reference to 'myla_Box.eq'` (the same with `impl<T: Ord> Ord for Rev<T>` and `<`). Calling the method, `Box { v: 1 }.eq(Box { v: 2 })`, links.
     ```myla fragment
     struct Box<T> {
         v: T,
     }

     impl<T> Eq for Box<T> {
         fun eq(self, other: Box<T>) -> bool {
             return true
         }
     }

     fun main() {
         print(Box { v: 1 } == Box { v: 2 })
     }
     ```
  2. A map type `[T: V]` with `T` a type parameter isn't checked where `T` is fixed: `one(P { a: 1 })` with `fun one<T>(x: T) -> [T: int]` and a struct `P` type-checks and runs in the interpreter (prints 1), and native code stops with "internal error: one__1P can't be lowered to the IR: an aggregate used as a scalar". So `Set<P>` of a struct passes the checker today. [[MYLA-313]] makes such keys real; until then the checker should reject the instance.
- **Diagnostics:** a module's mangled names show in messages: "cannot infer type parameter(s) T for 'std$set$new'", "`for ... in` requires a list or map, found 'std$set$Set<int32>'".

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-425]]: no `iter()`; `with_capacity(2^30 + 1)` hangs natively; the pages are [[MYLA-427]]'s.
