# std.cache

An LRU cache, `Lru<K, V>`, and memoising, `Memo<K, V>` ([[MYLA-404]]). A key is what a map key can be: a type that is `Eq` and `Hash` (D163), so `K: Eq + Hash`. The module imports `std.map`.

```myla
import std.cache as cache
from std.cache import Lru, Memo

// The number of ways to climb `n` steps one or two at a time, as a step: the
// value of `n` once those of `n - 1` and `n - 2` are known, else the key it
// needs first.
fun ways(n: int, known: [int: int64]) -> Result<int64, int> {
    if n < 2 {
        return Ok(1)
    }
    let a = match known.get(n - 1) {
        Some(a) => a,
        None => { return Err(n - 1) },
    }
    let b = match known.get(n - 2) {
        Some(b) => b,
        None => { return Err(n - 2) },
    }
    return Ok(a + b)
}

fun main() {
    var c: Lru<str, int> = cache.new(2)
    c.put("a", 1)
    c.put("b", 2)
    print(c.get("a").unwrap_or(0))
    match c.put("c", 3) {
        Some((k, v)) => print(f"evicted {k}={v}")
        None => print("room")
    }
    print(c.keys().join(" "))
    print(c.contains("b"))

    var lengths: Memo<str, int> = cache.new_memo((s: str) => s.len())
    print(lengths.get("hello") + lengths.get("hello"))
    print(lengths.len())

    var w: Memo<int, int64> = cache.recursive(ways)
    print(w.get(80))
    print(w.len())
}
// output:
// 1
// evicted b=2
// c a
// false
// 10
// 1
// 37889062373143906
// 81
```

## `Lru<K, V>`

| Function | Result |
| --- | --- |
| `new<K: Eq + Hash, V>(capacity: int) -> Lru<K, V>` | An empty cache that holds at most `capacity` entries (none for a `capacity` below 1) |

| Method | Result |
| --- | --- |
| `c.get(k: K) -> Option<V>` | The value of `k`, if it has one, which makes it the most recently used. Needs a `var` place |
| `c.put(k: K, v: V) -> Option<(K, V)>` | Sets the value of `k` and makes it the most recently used. When `k` is new and the cache full, the least recently used entry makes room and is the result; else `None`. A cache of no capacity keeps nothing and gives `(k, v)` back. Needs a `var` place |
| `c.peek(k: K) -> Option<V>` | The value of `k` without making it the most recently used |
| `c.contains(k: K) -> bool` | Whether `k` has an entry; not a use |
| `c.remove(k: K) -> Option<V>` | Takes the entry of `k` out: its value, if it had one. Needs a `var` place |
| `c.clear()` | Takes every entry out; the capacity stays. Needs a `var` place |
| `c.len() -> int`, `c.is_empty() -> bool`, `c.capacity() -> int` | The number of entries; whether there are none; the most it holds |
| `c.keys() -> [K]`, `c.items() -> [(K, V)]` | The keys, the entries, the most recently used first |

`unlink` and `link_front`, methods of `Lru`, are the cache's own steps on its recency list; a program has no need of them.

## `Memo<K, V>`

| Function | Result |
| --- | --- |
| `new_memo<K: Eq + Hash, V>(f: (K) -> V) -> Memo<K, V>` | A memo of `f`: `get(k)` is `f(k)`, computed once |
| `recursive<K: Eq + Hash, V>(step: (K, [K: V]) -> Result<V, K>) -> Memo<K, V>` | A memo of a recursive function, given as a step (below) |

| Method | Result |
| --- | --- |
| `m.get(k: K) -> V` | The value of `k`: the one kept, else computed and kept, with the values it needs. Needs a `var` place |
| `m.peek(k: K) -> Option<V>`, `m.contains(k: K) -> bool` | The value kept for `k`, without computing it; whether one is kept |
| `m.set(k: K, v: V)` | Keeps `v` as the value of `k`. Needs a `var` place |
| `m.len() -> int`, `m.clear()` | The number of values kept; forgets them all |

A memo grows without bound; one that should forget is an `Lru` used the same way: `get`, and on `None` compute and `put`.

### Recursion without references

A memoised recursive function has to reach the memo from inside itself, and a Myla closure can't: it captures copies, and a copy can't be changed, so a closure that called `m.get` would change a copy of the memo that is gone when it returns. So the function doesn't call the memo; the memo calls it, as a **step**: `step(k, known)` gets the values computed so far and returns `Ok(v)`, the value of `k`, when the ones it needs are in `known`, or `Err(j)`, a key whose value it needs first. `get(k)` keeps the keys it is computing on a stack of its own: it asks the step at the top of the stack, keeps the value an `Ok` gives and pops the key, or pushes the key an `Err` names, until `k` has its value. A step is asked again for each key it needs (the `ways` above, twice for each `n`). The stack is a list, so a recursion a million deep works where a recursive call would overflow the call stack (the interpreter's overflows below 20 000 calls). A step that needs a key that needs it, a cycle, is the failure `std.cache: a step needs a key that needs it (a cycle)`.

The other way is the one any Myla program has: the cache is the receiver of a `var self` method, which writes the caller's place, so a recursive call `self.at(n - 1)` leaves its values in the cache the outer call reads:

```myla
struct Ways {
    known: [int: int64],
}

impl Ways {
    fun at(var self, n: int) -> int64 {
        if n < 2 {
            return 1
        }
        if let Some(v) = self.known.get(n) {
            return v
        }
        let v = self.at(n - 1) + self.at(n - 2)
        self.known[n] = v
        return v
    }
}

fun main() {
    var w = Ways { known: [:] }
    print(w.at(80))
}
// output:
// 37889062373143906
```

It is twice as fast (natively, Fibonacci 10 000 deep: 0.99 ms against 1.91 ms for `recursive`) but is limited by the call stack.

## How it works

An `Lru` is a doubly linked list of indices, as Myla has no references: an entry lives in a slot of four lists (its key, its value, and the slots before and after it in the recency order, -1 at the ends), a map takes a key to its slot, and `head` and `tail` are the most and the least recently used slot. `get` moves the slot to the head; `put` of a new key into a full cache takes the tail's slot, `remove` puts its slot on a free list for the next `put`. Each is one or two map operations and a few index writes: constant time on average ([[MYLA-310]]'s removal). The slots never outnumber the capacity, and a slot keeps its old key and value until it is written again: a generic `V` has nothing else to fill it with.

Measured natively on x86-64 with [[Language/Standard-library/Bench]] (median of 5, 1 million operations on random keys, 2026-11-09):

| Work | `[int: int]` | `Lru<int, int>` |
| --- | --- | --- |
| `put`, 64k keys, capacity 64k | 23.0 ms | 45.2 ms |
| `put`, 128k keys, capacity 64k (evicting) | – | 124 ms |
| half `get`, half `put`, and a `get` of another key each, 128k keys | 68.1 ms | 92.4 ms (capacity 64k), 91.5 ms (256k) |
| `Memo` by `recursive`, Fibonacci 1 million deep | – | 486 ms |
