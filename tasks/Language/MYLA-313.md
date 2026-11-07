---
id: MYLA-313
title: "The Hash trait: every Eq + Hash type is a map key (D163)"
type: feature
status: review
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

- [x] `==` and `!=` on tuples whose elements are `Eq`, in the checker and every runner
- [x] The `Hash` trait and `Hasher` in the prelude; the built-in impls (integers, `char`, `bool`, `str`, tuples, lists)
- [x] `#derive(Hash)`: structs and enums, refusing float fields and a type without `Eq`
- [x] Map keys of any `Eq + Hash` type, natively on every target (generated hash and equality routines) and in the interpreter; the bound on a generic `[K: V]`, with the generic functions of `lib/` and `selfhost/` given it
- [x] Tests: test functions in every runner (`myla test --native`, the three targets), the error corpus for each refusal
- [x] [[Language/Methods-and-traits]], [[Language/Collections-and-strings]] and the skill updated

## Evidence

Built on b4b85d9 in four steps, each its own commit; the bootstrap reaches its byte-identical fixed point after each.

- **`==` on tuples and lists** of `Eq` elements, nested ones too: the checker (and `#derive(Eq)` over tuple and list fields), the interpreter (`values_equal`, element by element, a struct's own `eq` called as natively), native code (`__eq_<T>`, built as IR; a packed list's elements read at their width). Before: `(1, 2) == (1, 2)` was "cannot compare values of type '(int32, int32)'". The corpus file `type_tuple_equality.my` (D37's refusal) goes; two refusals are new.
- **The trait.** `struct Hasher { state: uint64 }` (with an `impl Eq`) and `trait Hash` are in the prelude, so every module names them; std.hash keeps the algorithm and the methods, gains `add<T: Hash>(self, x: T)` (`x.hash(self)`, a method with a bounded type parameter works as written) and the impls of the integers, `char`, `bool`, `str` and `[T: Hash]` (its length, then its elements), and is implicit (D164's list). A tuple's `hash` is the language's (`__thash_<T>` natively, element by element in the interpreter). Floats aren't `Hash`.
- **`#derive(Hash)`** writes the impl as source (`hasher.add(self.x)…`, an enum's variant index and its payload), parsed with fresh node ids, then checked and run like any other impl. It refuses a float field, a type without `Eq` and a type with its own `impl Hash` ([[examples/errors/type_derive_hash_float_field.my]], `…_without_eq`, `…_and_impl`). Derives are told apart by declaration id ([[MYLA-364]], fixed here).
- **Map keys.** The checker takes any `Eq + Hash` key ([[examples/errors/type_map_key_not_hash.my]], `…_float_tuple`, `…_struct_field`); a type parameter that is a map key in a signature has `Eq + Hash` by it, which callers must satisfy ([[examples/errors/type_map_key_implied_bound.my]]: `fun one<T>(x: T) -> [T: int]` with a struct, which the checker passed and native code stopped on), and one that keys a map only in a body needs it written (`…_generic_unbounded`). Natively a compound key's slot is `[state][hash][key][value][rank]`, with `__khash_<K>`, `__keq_<K>`, `__mfind_<K>`, `__mput_<K>` and `__mkeys_<K>` per key type and std.rt's `map_find_h`, `map_slot_h`, `map_keys_h`; the interpreter indexes such keys by hash, chained, compared with `==` (no linear search).
- **Generic functions given the bound: none needed editing.** std.map's `impl<K, V> [K: V]` (five methods) and `counts<T>`, and the prelude's `get`, have it implied by their signatures; `selfhost/` has no generic map. The seed couldn't have read a written `Hash` bound in std.map, which it compiles. std.set ([[MYLA-330]], not in this base) keys maps by `T` in its bodies and needs `T: Eq + Hash` written.

Tests, x86-64 unless said: `test_compiler_parity` (`tuple_and_list_equality`, `hash_trait_and_derive`, `compound_map_keys`: a grid BFS on `(int, int)`, struct, enum, list and case-insensitive keys, removes and reinserts in D105's order, generic code, std.map's methods; `test_compound_map_keys_are_released`), also under `scripts/test-target.py aarch64-linux` and `wasm32-wasi` (both suites pass); `STRESS_MAP_COMPOUND_KEY_SRC` in `test_selfhost_codegen` (struct and tuple keys holding strings and lists: peak 11 MB at 20,000 rounds and at 400,000); std.hash's 95 cases (two new test functions: the impls, `add`, derived hashes, compound keys) interpreted, `--native`, on aarch64 and on wasm32; the error corpus; the checker's `errors_of` cases; `test_map_remove`, `test_map_order`, `test_selfhost_interp`, `test_selfhost_codegen`, `test_std_modules`, `test_modules` (MYLA-364).

Measured natively (x86-64, best of five, a machine shared with other work), 1M inserts then 1M lookups:

| Map | base (b4b85d9) | this branch |
| --- | --- | --- |
| `[int: int]` | 147 ms / 33 ms | 143 ms / 32 ms |
| `[str: int]` | 260 ms / 73 ms | 285 ms / 74 ms (noise: the same code) |
| `[int64: int]`, `(x, y)` packed by hand | 150 ms / 28 ms | 151 ms / 28 ms |
| `[(int, int): int]` | (refused) | 210 ms / 63 ms |

The integer and string maps' code is unchanged. A tuple key costs 1.4 times the packed key's insert and 2.2 times its lookup (a call of the hash routine, then of the equality routine for the candidate). `myla run` of a hello world takes 40 ms instead of 32, std.hash being checked with every program; its binary is the same size.
