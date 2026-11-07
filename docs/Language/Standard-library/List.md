# std.list

Methods on lists ([[MYLA-323]], D164): building, higher-order operations taking closures, sorting, searching a sorted list, and combinatorics. They are in `impl<T> [T]` blocks, so every list has them once the module is imported; the ones that compare elements need `T: Eq`, `T: Ord` or `T: Add`, and `join` is a method of `[str]` only. The receiver is a copy, so a method that returns a new list copies the elements only when the list is shared (copy-on-write). A method that changes its list is a `var self` method and needs a `var` place (`xs.sort()`); one that returns a new list has a past participle or a noun (`xs.sorted()`). The names are Rust's, where Rust has the operation.

```myla
import std.list as list

struct Run {
    name: str,
    secs: int,
}

fun main() {
    let xs = [5, 3, 8, 1, 9, 2]
    print(xs.filter((x) => x % 2 == 1).map((x) => f"<{x}>").join(" "))
    print(xs.fold(0, (acc, x) => acc + x))
    var ys = xs
    ys.sort()
    print(ys.map((x) => f"{x}").join(","))
    print(ys.lower_bound(4))
    var runs = [Run { name: "ann", secs: 31 }, Run { name: "bob", secs: 27 }, Run { name: "cy", secs: 31 }]
    runs.sort_by_key((r) => r.secs)
    print(runs.map((r) => r.name).join(" "))
    print(list.filled(3, "ab").join(""))
    print([1, 2, 3].permutations().len())
}
// output:
// <5> <3> <1> <9>
// 28
// 1,2,3,5,8,9
// 3
// bob ann cy
// ababab
// 6
```

A lambda's parameter types can be left out: the receiver's element type gives them (`xs.map((x) => x * 2)`, [[MYLA-356]]).

[TOC]

## Building

| Item | Meaning |
| --- | --- |
| `filled<T>(n: int, v: T) -> [T]` | A function, there being no receiver: `n` copies of `v` (none when `n` isn't positive) |
| `reversed() -> [T]` | The elements in the opposite order |
| `concat(other: [T]) -> [T]` | The elements, then `other`'s |
| `extend(var self, other: [T])` | Adds `other`'s elements at the end |
| `insert(var self, i: int, v: T)` | Puts `v` at `i`, moving the rest up; `i` may be the length. Another index is a runtime error |
| `remove_at(var self, i: int) -> T` | Takes out the element at `i` and returns it (Rust's `remove`; a map's `remove(k)` takes a key) |
| `swap(var self, i: int, j: int)` | Exchanges two elements |
| `truncate(var self, n: int)` | Keeps the first `n` elements |
| `dedup(var self)`, `T: Eq` | Removes each element equal to the one before it (every repeat, in a sorted list) |
| `contains(v: T) -> bool`, `T: Eq` | Whether some element is `v` |
| `index_of(v: T) -> Option<int>`, `T: Eq` | The index of the first element that is `v` |
| `join(sep: str) -> str`, on `[str]` | The strings with `sep` between each two |

## Higher-order operations

| Item | Meaning |
| --- | --- |
| `map<U>(f: (T) -> U) -> [U]` | `f` of each element |
| `filter(keep: (T) -> bool) -> [T]` | The elements `keep` holds for, in order |
| `fold<A>(init: A, f: (A, T) -> A) -> A` | `f(… f(init, x0) …, xn)`; `init` for an empty list |
| `reduce(f: (T, T) -> T) -> Option<T>` | `fold` from the first element; `None` for an empty list |
| `any(pred)`, `all(pred) -> bool` | Whether `pred: (T) -> bool` holds for some, for every element (false, true for an empty list) |
| `find(pred) -> Option<T>`, `position(pred) -> Option<int>` | The first element `pred` holds for, its index |
| `count(pred) -> int` | How many elements `pred` holds for |
| `sum(zero: T) -> T`, `T: Add` | The elements added to `zero`: `xs.sum(0)`, `xs.sum(0.0)`. Myla has no zero of a generic `T`, so the caller gives it |
| `min_by(less)`, `max_by(less) -> Option<T>` | The least and greatest element by `less: (T, T) -> bool`, "a goes before b": the first of equal least ones, the last of equal greatest ones, as Rust's |
| `flat_map<U>(f: (T) -> [U]) -> [U]` | The lists `f` gives, one after the other |
| `zip<U>(other: [U]) -> [(T, U)]` | Pairs of the elements at the same index, as many as the shorter list has |
| `enumerate() -> [(int, T)]` | Each element with its index |
| `chunks(n: int) -> [[T]]` | The elements in lists of `n`, the last one shorter when they don't divide evenly |
| `windows(n: int) -> [[T]]` | Every run of `n` adjacent elements, overlapping (none for a shorter list) |

`chunks` and `windows` take a positive size; another is a runtime error.

## Sorting

| Item | Meaning |
| --- | --- |
| `sort(var self)`, `T: Ord` | Ascending, stable: equal elements keep their order. A merge sort: runs of 16 by insertion, then passes merging pairs of runs |
| `sort_by(var self, less: (T, T) -> bool)` | The same by `less`, "a goes before b" (`(a, b) => a > b` sorts descending) |
| `sort_by_key<K: Ord>(var self, key: (T) -> K)` | Stable, by the keys `key` gives, calling it once for each element |
| `sorted() -> [T]`, `T: Ord`; `sorted_by(less) -> [T]` | A sorted copy |
| `sort_unstable(var self)`, `T: Ord` | Ascending, faster but without keeping equal elements in order: an introsort (a quicksort with the median of three, a heapsort where it goes too deep, insertion sort for short ranges), so never quadratic |
| `is_sorted() -> bool`, `T: Ord` | Whether every element is at least the one before it |

Sorting 1 million `int`s natively (x86-64, 4 cores of a shared Xeon at 2.3 GHz, the numbers of `benchmarks/quicksort`, 2026-11-07). The times are the medians of three sets of 5 runs, which differed by up to 15 %; the instructions are exact:

| Sort | Time | Instructions (callgrind) |
| --- | ---: | ---: |
| `sort` | 125 ms | 918 M |
| `sort_unstable` | 92 ms | 455 M |
| `sort_by((a, b) => a < b)` | 150 ms | 1,154 M |
| `benchmarks/quicksort`'s generic `sort` | 105 ms | 569 M |
| Advent of Code's merge sort (`lib/aoc/sort.my`, [[Project/AoC-2015-2021]]) | 285 ms | |
| C's `qsort` (glibc, gcc `-O2`) | 110 ms | |

The stable sort takes twice the unstable sort's instructions but only about a third more time. Through a closure each comparison is a call: `sort_by` takes a fifth more than `sort`.

## Searching a sorted list

The list must be sorted ascending (by `<`, or for `partition_point` by its predicate).

| Item | Meaning |
| --- | --- |
| `binary_search(v: T) -> Result<int, int>`, `T: Ord` | `Ok` of the index of the first element equal to `v`, or `Err` of the index where `v` would go |
| `lower_bound(v: T) -> int`, `T: Ord` | The first index whose element isn't less than `v` |
| `upper_bound(v: T) -> int`, `T: Ord` | The first index whose element is greater than `v` |
| `partition_point(pred: (T) -> bool) -> int` | The first index `pred` fails for, where it holds for a first part and fails for the rest |

## Combinatorics

| Item | Meaning |
| --- | --- |
| `permutations() -> [[T]]` | Every order of the elements, n! of them, in the lexicographic order of their positions (a sorted list's in lexicographic order); equal elements give equal orders. `[[]]` for an empty list |
| `combinations(k: int) -> [[T]]` | Every choice of `k` elements, each in the list's order, in the lexicographic order of their positions; `[[]]` for `k` = 0, none for a `k` greater than the length |
| `next_permutation(var self) -> bool`, `T: Ord` | Rearranges into the next greater order and says whether there was one; after the greatest it gives the least (ascending) and false, as C++'s does, so `while xs.next_permutation() { … }` visits each distinct order once from a sorted start |

## Tests

`#test` can't take a generic function or a method of a generic impl (D116), so the module's cases are test functions (D162) that call the methods on concrete lists: `myla test lib/std/list.my`, interpreted and with `--native`. The module doesn't import `std.test`, which would come into every program with it.
