# std.btree

A sorted map and a sorted set ([[MYLA-343]]). `SortedMap<K, V>` keeps its keys in order, so it finds the greatest key below a value, the least above it, or every key in a range; `SortedSet<T>` is a sorted map to `()`. Both are B+ trees, and their keys are of any ordered type (`K: Ord`). The module imports std.list and std.option.

```myla
import std.btree as btree
from std.btree import SortedMap, SortedSet

fun main() {
    var events: SortedMap<int, str> = btree.new()
    events.insert(930, "standup")
    events.insert(1300, "lunch")
    events.insert(1100, "review")
    events.insert(1600, "retro")
    print(events.keys().map((t) => f"{t}").join(" "))
    // The event under way at 12:15, and the next one
    print(events.floor(1215).map((e) => e.1).unwrap_or("-"))
    print(events.ceiling(1215).map((e) => e.1).unwrap_or("-"))
    print(events.range(1000, 1400).map((e) => e.1).join(", "))
    print(events.pop_first().map((e) => e.1).unwrap_or("-"))
    print(events.len())
    let a: SortedSet<str> = btree.set_of(["pear", "fig", "apple", "fig"])
    let b: SortedSet<str> = btree.set_of(["fig", "kiwi"])
    print(a.items().join(" "))
    print(a.union(b).items().join(" "))
    print(a.difference(b).items().join(" "))
}
// output:
// 930 1100 1300 1600
// review
// lunch
// review, lunch
// standup
// 3
// apple fig pear
// apple fig kiwi pear
// apple pear
```

| Function | Result |
| --- | --- |
| `new<K: Ord, V>() -> SortedMap<K, V>` | An empty sorted map |
| `of<K: Ord, V>(pairs: [(K, V)]) -> SortedMap<K, V>` | The map of the pairs; of a key given twice, the later value |
| `set_new<T: Ord>() -> SortedSet<T>` | An empty sorted set |
| `set_of<T: Ord>(xs: [T]) -> SortedSet<T>` | The set of the elements of `xs` |

| Method of `SortedMap<K, V>` | Result |
| --- | --- |
| `m.insert(k: K, v: V) -> Option<V>` | Sets `k` to `v`, in O(log n); the value `k` had, if it was there. Needs a `var` place |
| `m.get(k: K) -> Option<V>` | The value of `k`, in O(log n) |
| `m.contains(k: K) -> bool` | Whether `k` is there |
| `m.remove(k: K) -> Option<V>` | Removes `k`, in O(log n); the value it had. Needs a `var` place |
| `m.len() -> int`, `m.is_empty() -> bool` | The number of keys; whether there are none |
| `m.first() -> Option<(K, V)>`, `m.last() -> Option<(K, V)>` | The least key and its value; the greatest |
| `m.floor(k: K) -> Option<(K, V)>` | The greatest key not greater than `k`, and its value |
| `m.ceiling(k: K) -> Option<(K, V)>` | The least key not less than `k`, and its value |
| `m.range(lo: K, hi: K) -> [(K, V)]` | The keys from `lo` up to but not including `hi`, with their values, in order; none when `hi` isn't greater than `lo`. O(log n) and then the keys found |
| `m.keys() -> [K]`, `m.values() -> [V]`, `m.items() -> [(K, V)]` | The keys in order, the values in their keys' order, both together |
| `m.iter() -> SortedMapIter<K, V>` | An iterator over the keys with their values, in order (D171) |
| `m.pop_first() -> Option<(K, V)>`, `m.pop_last() -> Option<(K, V)>` | Takes the least key and its value; the greatest. Need a `var` place |

| Method of `SortedSet<T>` | Result |
| --- | --- |
| `s.insert(x: T) -> bool` | Adds `x`; true if it wasn't there. Needs a `var` place |
| `s.remove(x: T) -> bool` | Removes `x`; true if it was there. Needs a `var` place |
| `s.contains(x: T) -> bool` | Whether `x` is in the set |
| `s.len() -> int`, `s.is_empty() -> bool` | The number of elements; whether there are none |
| `s.first() -> Option<T>`, `s.last() -> Option<T>` | The least element; the greatest |
| `s.floor(x: T) -> Option<T>`, `s.ceiling(x: T) -> Option<T>` | The greatest element not greater than `x`; the least not less than `x` |
| `s.range(lo: T, hi: T) -> [T]` | The elements from `lo` up to but not including `hi`, in order |
| `s.items() -> [T]` | The elements, in order |
| `s.iter() -> SortedSetIter<T>` | An iterator over the elements, in order (D171) |
| `s.pop_first() -> Option<T>`, `s.pop_last() -> Option<T>` | Takes the least element; the greatest. Need a `var` place |
| `s.union(other) -> SortedSet<T>` | The elements of either, in O(n + m) |
| `s.intersection(other) -> SortedSet<T>` | The elements of both, in O(n + m) |
| `s.difference(other) -> SortedSet<T>` | The elements of `s` that `other` hasn't, in O(n + m) |
| `s.is_subset(other) -> bool` | Whether every element of `s` is in `other` |

A range is half-open, as Myla's ranges are: `m.range(10, 20)` holds 10 and not 20. `for x in s.iter()` and `for (k, v) in m.iter()` visit the tree in order, a leaf at a time, without making a list ([[MYLA-425]]): over a million entries natively 7 to 9 ms against 12 to 16 ms for `items()`. `iter()` starts a pipeline of [[Language/Standard-library/Iter]] (D171); the iterator holds the tree as it was when `iter()` was called, and a copy of it keeps its own position.

## Keys

A key is of any type that is `Ord`: the integers, the floats, `char`, `str` (byte by byte, D165), and a type with an `impl Ord` of its own (`fun cmp(self, other: Self) -> int`). Two keys are the same key when neither is less than the other, so a type's own `cmp` decides it: a `cmp` that returns 0 for two different values makes them one key, and `insert` replaces the value (the key stays the first one inserted). A float NaN is neither less nor greater than anything, so don't use it as a key.

## Making one

A map's types come from where it goes ([[MYLA-315]]): an annotation (`var m: SortedMap<str, int> = btree.new()`), a field, a parameter or a return type. With nothing expected, `let m = btree.new()` is an error, "cannot infer type parameter(s) K, V": annotate the binding. `of` and `set_of` take their types from their list, unless it is `[]`. A sorted map or set is a value: a copy changes on its own, and its first change copies the list of nodes, then each node it writes.

## How it works

A B+ tree: the keys and values are in the leaves, which are linked in key order, and an inner node holds keys that only route a search, one fewer than its children. Every leaf is at the same depth. A node has at most 63 keys (`ORDER` is 64 children), and every node but the root has at least 31, so a million keys take four levels.

Myla has no references, so the tree is an arena: the nodes are a list, and an inner node names its children by their index there. A node's keys, values and children are lists of their own. An update changes the nodes on its path in place, since each is the only copy of itself; a node that a removal frees goes on a list of free slots, which the next new node takes.

Updates are top-down, in one pass: an insert splits a full child before it enters it, and a removal gives a child at the minimum a key from a sibling that can spare one, or merges the two, before it enters it. So the leaf it ends at has room, or a key to spare, and nothing travels back up. A search within a node halves its range down to 8 keys and then goes on one key at a time, which branches more predictably than halving to the end.

`union`, `intersection` and `difference` merge the two sets' elements and build the result's tree from the sorted list, level by level, in O(n + m).

## Speed

Measured natively on x86-64, best of five runs, with a million random `int` keys (a few repeat), 2026-11-08, `d0e4f0c`:

| Work | Time |
| --- | --- |
| 1 million `insert`, `SortedMap<int, int>` | 369 ms (`[int: int]`: 148 ms) |
| 1 million `get` of them | 253 ms (`[int: int]`: 34 ms) |
| 1 million `range` of about 10 keys each | 421 ms |
| 1 million `remove` | 502 ms (`[int: int]`: 32 ms) |
| 1 million `insert`, `SortedSet<int>` | 345 ms (std.set's `Set<int>`: 132 ms) |
| 1 million `contains` | 243 ms (`Set<int>`: 26 ms) |

The hash map is seven times as fast to look up in: it reaches a key in one probe, the tree in a search per level, four levels of nodes spread over memory. Take a sorted map for what a hash map can't do: the keys in order, `floor`, `ceiling` and `range`.

What was measured on the way, for 1 million inserts and gets of `int`:

| Layout | Insert | Get |
| --- | --- | --- |
| The arena of this module, `ORDER` 64 | 335 ms | 246 ms |
| A nested tree of enum values, `enum Tree { Leaf([int], [int]), Inner([int], [Tree]) }`, each update copying its path | 1636 ms | 283 ms |
| A flat arena: every node's keys in one list, `MAX_KEYS` slots per node | 284 ms | 193 ms |

The flat arena is a sixth faster to insert into and a fifth to look up in, but its free slots must hold something, and a generic `K` or `V` has no empty value: they would hold copies of keys and values that are gone, as a deque's free slots do, and keep them alive. The node lists keep only what is in the map.

`ORDER`, the most children of a node, tuned by the same measurement with a remove of each key after:

| `ORDER` | Insert | Get | Remove |
| --- | --- | --- | --- |
| 32 | 377 ms | 293 ms | 515 ms |
| 48 | 344 ms | 258 ms | 498 ms |
| 64 | 360 ms | 251 ms | 503 ms |
| 96 | 369 ms | 249 ms | 554 ms |
| 128 | 383 ms | 252 ms | 570 ms |

A search to the end by halving took 279 ms for the million gets, one by one from 8 keys 244 ms, one by one through the whole node 235 ms; 8 keeps the number of comparisons low for a key that is expensive to compare, such as a `str`. Halving with `(lo + hi) / 2` instead of `>> 1` cost a fifth of a lookup, as the native backend divides by 2 with `idiv`. An insert takes the node's lists out of the node before it shifts them, so that each write goes to the list and not through the node: 420 ms became 351.
