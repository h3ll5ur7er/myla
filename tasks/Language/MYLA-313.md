---
id: MYLA-313
title: "The Hash trait: every Eq + Hash type is a map key (D163)"
type: feature
status: todo
priority: medium
labels: [maps, tuples, traits, derive]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F4). `[(int, int): int]` is rejected with "map key type must be a primitive (integer, char, bool, or str), found '(int32, int32)'", and `(1, 2) == (1, 2)` with "cannot compare values of type '(int32, int32)'". So every grid and every state search packs its key into an `int64` by hand: about 50 calls to `pack(x, y)`, plus custom encodings on 2016 Day 11 and 2018 Day 18. Packing works, but a bad encoding collides silently.

## Decided (D163, 2026-11-07)

A map's key type is any type that is `Eq + Hash`:

```myla fragment
trait Hash {
    fun hash(self, h: Hasher) -> Hasher
}

#derive(Eq, Hash)
struct Pos { x: int, y: int }

fun main() {
    var seen: [Pos: int] = [:]
    seen[Pos { x: 1, y: 2 }] = 3
    var pairs: [(int, str): bool] = [:]
    pairs[(1, "a")] = true
}
```

- The hasher's state is passed through by value, since Myla has no `var` parameters. A derived impl adds the fields in order (`h.add(self.x).add(self.y)`), and for an enum the variant and its payload. The algorithm is `std.hash`'s ([[MYLA-327]]).
- The integers, `char`, `bool` and `str` are `Hash`. A tuple is `Hash` when its elements are, and so is a list. Floats aren't: `#derive(Hash)` refuses a float field, and a hand-written impl may hash `to_bits`.
- `#derive(Hash)` needs an `Eq` of the type, derived or written. That `a == b` gives equal hashes is a hand-written impl's promise, which the docs state.
- A generic `[K: V]` needs `K: Eq + Hash`. Today the key type is only checked when a generic function is instantiated.
- Natively, a compound key gets two routines per key type, hash and equality, generated as the drop and copy routines are. Primitive and `str` keys keep today's fast path in `std.rt`. The interpreter calls the trait's method.

## Order

After [[MYLA-310]] (the same map routines), [[MYLA-315]] (the same checker code) and [[MYLA-327]] (the hasher).

- [ ] `==` and `!=` on tuples whose elements are `Eq`, in the checker and every runner
- [ ] The `Hash` trait and `Hasher` in the prelude; the built-in impls (integers, `char`, `bool`, `str`, tuples, lists)
- [ ] `#derive(Hash)`: structs and enums, refusing float fields and a type without `Eq`
- [ ] Map keys of any `Eq + Hash` type, natively on every target (generated hash and equality routines) and in the interpreter; the bound on a generic `[K: V]`, with the generic functions of `lib/` and `selfhost/` given it
- [ ] Tests: test functions in every runner (`myla test --native`, the three targets), the error corpus for each refusal
- [ ] [[Language/Methods-and-traits]], [[Language/Collections-and-strings]] and the skill updated
