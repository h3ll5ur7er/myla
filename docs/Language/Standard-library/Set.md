# std.set

`Set<T>`, a set of values that keeps the order in which they were inserted ([[MYLA-330]]). It is a map from its elements to `()`, so it has the map's order (D105) and its average constant time for `insert`, `remove` and `contains` ([[MYLA-310]]). The module imports nothing.

```myla
import std.set as set
from std.set import Set

fun main() {
    var seen: Set<str> = set.new()
    for w in ["to", "be", "or", "not", "to", "be"] {
        if !seen.insert(w) {
            print(f"again: {w}")
        }
    }
    print(seen.len())
    let vowels: Set<char> = set.of("aeiou".chars())
    let word: Set<char> = set.of("education".chars())
    var common = ""
    for c in word.intersection(vowels).items() {
        common += f"{c}"
    }
    print(common)
    print(vowels.is_subset(word))
    print(word.difference(vowels).len())
}
// output:
// again: to
// again: be
// 4
// euaio
// true
// 4
```

| Function | Result |
| --- | --- |
| `new<T>() -> Set<T>` | An empty set |
| `of<T>(xs: [T]) -> Set<T>` | The elements of `xs`, in the order they first occur there |

| Method | Result |
| --- | --- |
| `s.insert(x: T) -> bool` | Adds `x`; true if it wasn't there. An element already there keeps its place. Needs a `var` place |
| `s.remove(x: T) -> bool` | Removes `x`; true if it was there. Needs a `var` place |
| `s.contains(x: T) -> bool` | Whether `x` is in the set |
| `s.len() -> int`, `s.is_empty() -> bool` | The number of elements; whether there are none |
| `s.items() -> [T]` | The elements, in insertion order |
| `s.union(other) -> Set<T>` | The elements of either: `s`'s, then those of `other` that `s` hasn't, each in its set's order |
| `s.intersection(other) -> Set<T>` | The elements of both, in `s`'s order |
| `s.difference(other) -> Set<T>` | The elements of `s` that `other` hasn't, in `s`'s order |
| `s.is_subset(other) -> bool` | Whether every element of `s` is in `other` |

The order is the map's: an element inserted again keeps its place, one removed and inserted again goes last.

## Elements

An element is what a map key can be: an integer, `char`, `bool` or `str`. The set asks nothing more of `T` than the map does, so once [[MYLA-313]] makes tuples and structs that derive `Eq` and `Hash` keys (D163), they are elements too, with no change to `std.set`.

## Making one

A set's element type comes from where the set goes ([[MYLA-315]]): an annotation (`var s: Set<int> = set.new()`), a field, a parameter or a return type. With nothing expected, `let s = set.new()` is an error, "cannot infer type parameter(s) T": annotate the binding. `set.of(xs)` takes its type from `xs`, unless `xs` is `[]`.

## Visiting the elements

`for x in s` isn't possible yet: a `for` loop takes a list, a map or a range, and a type of one's own needs an iterator trait ([[MYLA-353]]). Write `for x in s.items()`, which visits a copy of the elements in insertion order.

## Speed

Measured natively on x86-64, best of five runs:

| Work | Time |
| --- | --- |
| 1 million `insert`, then 1 million `remove`, of random `int` | 148 ms (a bare `[int: ()]` map: 153 ms) |
| Breadth-first search of a 1000×1000 grid, `Deque` and a `Set<int>` of the cells seen | 156 ms (a bare map: 141 ms) |
| The same search with a `[bool]` per cell | 19 ms |

The set costs what its map costs. When the elements are small integers, such as the cells of a grid, a `[bool]` of them is eight times faster.
