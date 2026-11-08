# std.map

Methods on maps `[K: V]`, and `counts`, which counts a list's elements ([[MYLA-324]], D164). A map keeps its keys in insertion order (D105): a key written again keeps its place, one removed and added again goes last. `values` and `items` follow that order, as `keys()` and `for k in m` do. The builtin methods `len`, `contains`, `keys` and `remove` stay the builtins' (D151, [[Language/Collections-and-strings#Maps]]), and `get(m, k)`, which gives an `Option`, the prelude's.

```myla
from std.map import counts

fun main() {
    var stock: [str: int] = [:]
    stock["pears"] = 4
    stock["figs"] = 0
    stock.update("pears", 0, (n) => n - 1)
    stock.update("plums", 0, (n) => n + 6)
    print(stock.get_or("figs", -1))
    print(stock.get_or("kiwis", -1))

    var delivery: [str: int] = [:]
    delivery["figs"] = 12
    delivery["limes"] = 3
    stock.merge(delivery)
    for kv in stock.items() {
        let (fruit, n) = kv
        print(f"{fruit}: {n}")
    }
    var total = 0
    for n in stock.values() { total += n }
    print(total)

    let letters = counts("banana".chars())
    print(f"{letters['a']} a, {letters['n']} n, {letters['b']} b")
}
// output:
// 0
// -1
// pears: 3
// figs: 12
// plums: 6
// limes: 3
// 24
// 3 a, 2 n, 1 b
```

| Item | Meaning |
| --- | --- |
| `m.get_or(k: K, default: V) -> V` | The value of `k`, or `default` when the map has no `k` |
| `m.update(k: K, default: V, f: (V) -> V)` | Sets `k` to `f` of its value, or of `default` when the map has no `k` (a new key goes last); needs a `var` place |
| `m.values() -> [V]` | The values, in the order of their keys |
| `m.items() -> [(K, V)]` | The entries as `(key, value)` pairs, in insertion order |
| `m.iter() -> ListIter<(K, V)>` | An iterator over the same pairs, in the same order (D171): the source of a lazy pipeline of [[Language/Standard-library/Iter]], `m.iter() \|> iter.filter((kv) => kv.1 > 0)`. It is `items()`'s list as `std.list`'s `ListIter`, so it holds a copy of the entries the map had when it was made |
| `m.merge(other: [K: V])` | Adds every entry of `other`, whose value wins for a key both have; `other`'s new keys go last, in its order; needs a `var` place |
| `counts<T: Eq + Hash>(xs: [T]) -> [T: int]` | How often each element of `xs` occurs, the elements in the order they first occur |

`m.get_or(k, 0)` reads what `match get(m, k) { Some(v) => v, None => 0 }` says, the most common use of `get` in the Advent of Code solutions (14 of 29, [[MYLA-318]]). `update`'s function takes its parameter's type from the map (`(n) => n + 1`), as the value type is known from the receiver. A `for` head takes no tuple pattern, so a loop over `items()` takes each pair apart with `let`.
