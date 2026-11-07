---
id: MYLA-313
title: "Tuples and structs as map keys: structural == and hashing"
type: feature
status: backlog
priority: medium
labels: [maps, tuples, traits, decision]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F4). `[(int, int): int]` is rejected with "map key type must be a primitive (integer, char, bool, or str), found '(int32, int32)'", and `(1, 2) == (1, 2)` with "cannot compare values of type '(int32, int32)'". So every grid and every state search packs its key into an `int64` by hand: about 50 calls to `pack(x, y)`, plus custom encodings on 2016 Day 11 and 2018 Day 18. Packing works, but a bad encoding collides silently.

## Suggested shape (for the owner)

1. **Structural `==` on tuples** whose elements are `Eq`, as `#derive(Eq)` does for a struct.
2. **Tuples as keys:** the map's hash and compare routines generated per key type, as the per-type drop and copy routines already are (`std.rt`, the lowering's generated IR functions). A tuple of primitives hashes its elements in order.
3. **Structs and enums as keys:** a `Hash` trait, derivable beside `Eq` (`#derive(Eq, Hash)`), or a key type allowed when it derives `Eq` and every field is a valid key type. A decision of its own: a user-written `Hash` needs a hasher type in `std`, and a derived one needs only the generated routine.
4. **Sets** ([[Project/Standard-library-roadmap]]) and `Ord` for tuples (sorting by several fields) follow from the same routines.

- [ ] Decision: tuples first, then derived structs; `Hash` as a trait or as a derive only
- [ ] `==` and `!=` on tuples, in the checker and every runner
- [ ] Tuple keys in maps, natively on every target and in the interpreter
- [ ] Struct and enum keys
