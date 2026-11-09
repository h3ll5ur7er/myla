# std.bitset

`BitSet`, a set of small non-negative integers that takes a bit for each ([[MYLA-342]]). The integer `i` is bit `i % 64` of the word `i / 64`, a `uint64`, so a set of the integers below n takes n / 8 bytes and the set operations work 64 integers at a time. A set is growable, making room for whatever is inserted, or fixed, holding 0 to n - 1. The module imports nothing.

```myla
import std.bitset as bitset
from std.bitset import BitSet

// The primes below n, by the sieve of Eratosthenes.
fun primes(n: int) -> BitSet {
    var b = bitset.fixed(n).complemented()
    b.remove(0)
    b.remove(1)
    var p = 2
    while p * p < n {
        if b.contains(p) {
            var m = p * p
            while m < n {
                b.remove(m)
                m += p
            }
        }
        p += 1
    }
    return b
}

fun main() {
    let ps = primes(100)
    print(ps.popcount())
    print(ps.items()[:8].map((i) => f"{i}").join(" "))
    print(ps.next_from(90).unwrap_or(-1))

    var keys = bitset.new()
    keys.insert(3)
    keys.insert(70)
    print(f"{keys.popcount()} keys, room for {keys.capacity()}")
    let doors = bitset.of([3, 5, 70])
    print(doors.difference(keys).items().map((i) => f"{i}").join(" "))
    print(keys.is_subset(doors))
    print(keys.union(doors) == doors)
    var seen: [BitSet: int] = [:]
    seen[keys] = 1
    keys.insert(5)
    keys.remove(5)
    print(seen.contains(keys))
}
// output:
// 25
// 2 3 5 7 11 13 17 19
// 97
// 2 keys, room for 128
// 5
// true
// true
// true
```

| Function | Result |
| --- | --- |
| `new() -> BitSet` | An empty growable set |
| `fixed(n: int) -> BitSet` | An empty set that holds the integers 0 to n - 1 and no others. A negative `n` is a failure |
| `of(xs: [int]) -> BitSet` | A growable set of the integers of `xs` |

| Method | Result |
| --- | --- |
| `b.insert(i: int) -> bool` | Adds `i`; true if it wasn't there. A growable set grows; a fixed set fails for an `i` it can't hold, and every set for a negative `i`, as a list index out of bounds does. Needs a `var` place |
| `b.remove(i: int) -> bool` | Removes `i`; true if it was there. Needs a `var` place |
| `b.toggle(i: int) -> bool` | Removes `i` if it is there, else inserts it; true if it is there now. Needs a `var` place |
| `b.contains(i: int) -> bool` | Whether `i` is in the set; false for any integer it can't hold |
| `b.popcount() -> int` | The number of integers in the set |
| `b.is_empty() -> bool` | Whether there are none |
| `b.capacity() -> int` | What it holds without growing, 0 to `capacity() - 1`: a fixed set's size, or a multiple of 64 above a growable set's greatest integer |
| `b.items() -> [int]` | The integers, ascending |
| `b.next_from(i: int) -> Option<int>` | The least integer of the set that is `i` or more |
| `b.union(other) -> BitSet` | The integers of either set, in a set of `b`'s kind: a fixed `b` fails if it can't hold them, as `insert` does |
| `b.intersection(other) -> BitSet` | The integers of both, in a set of `b`'s kind and size |
| `b.difference(other) -> BitSet` | `b`'s integers that `other` hasn't, of `b`'s kind and size |
| `b.symmetric_difference(other) -> BitSet` | The integers of one but not both, of `b`'s kind, as for `union` |
| `b.complemented() -> BitSet` | The integers below n that a fixed set of size n hasn't. A growable set's complement would have no end: a failure |
| `b.is_subset(other) -> bool`, `b.is_disjoint(other) -> bool` | Whether every integer of `b` is in `other`; whether they share none |
| `b.cleared() -> BitSet` | An empty set of `b`'s kind and size |

`used`, `trim` and `reserve` are the set's own steps; a program has no need of them.

## Visiting the integers

`for i in b.items()` visits them in order. `next_from` does without the list:

```myla fragment
var at = b.next_from(0)
while let Some(i) = at {
    // … i …
    at = b.next_from(i + 1)
}
```

`for i in b` isn't possible yet ([[MYLA-353]]).

## Equality and keys

A `BitSet` has `#derive(Eq, Hash)`, so it is compared with `==`, is a map key and is a `Set` element: the state of a search over subsets, such as the keys collected in a maze. That works because every set has one form. A growable set ends in a word that isn't zero (`remove` and the operations drop the zero words at the end), and a fixed set of size n has `(n + 63) / 64` words with the bits from n on clear. So:

- two growable sets are equal when they hold the same integers, however they got there;
- two fixed sets are equal when they have the same size too;
- a fixed set never equals a growable one: compare `items()` across kinds.

A written `impl Hash` that skipped the zero words would have let any two sets of the same integers be equal; the one form per set lets the derived `Eq` and `Hash` say the same without one.

## Speed

Measured natively on x86-64, best of five runs:

| Work | Time |
| --- | --- |
| The sieve above, to 10 million, with a fixed `BitSet` | 107 ms |
| The same with a `[bool]` | 81 ms |
| `union`, `intersection` and their `popcount`s, of two sets of a million bits, 100 times | 11 ms |

A `[bool]` is faster for one bit at a time, where each `BitSet` call checks its bounds; the bit set takes a bit per integer (1.25 MB for 10 million) and does the set operations a word at a time. The counting is a SWAR popcount, the module's own: std.int's `count_ones` is the same, but importing std.int would make every program that imports this module parse std.int's cases, 12 ms more to check a hello world, and only the module's own functions are inlined ([[MYLA-376]]).
