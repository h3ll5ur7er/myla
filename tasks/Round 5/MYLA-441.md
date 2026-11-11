---
id: MYLA-441
title: "Native `map key … not found` for struct, enum and list keys"
type: improvement
status: review
priority: low
labels: [lowering, runtime, round-5]
---
Found by [[MYLA-415]] (D183). Natively a missing key of an integer, `char`, `bool` or string type, or a tuple of such, is written as the interpreter writes it (`map key (3, 'b') not found`); a key of a struct, an enum or a list type, or a tuple holding one, still gives `map key not found` (`Lower.key_text_of` returns -1), where the interpreter says `map key P { x: 1 } not found`, `map key Color.Red not found` or `map key [1, 2] not found`. So such an error can't be expected with its text on both runners (D183).

```myla
#derive(Eq, Hash)
struct P { x: int }
fun main() {
    let m = [P { x: 0 }: 1]
    print(m[P { x: 1 }])
}
```

- [x] Per-type routines writing the interpreter's `py_repr` of a struct, an enum (with its payloads) and a list, built as IR like `__eq_T` (or in Myla source, as the native harness writes its reprs), called on the cold path only
- [x] Cases in `test_runtime_errors_carry_the_interpreters_values`

## Evidence

Built as IR (`selfhost/lower.my`): `key_text_of` writes a scalar or string key as before (`repr_scalar`) and any compound key through `repr_member`, which calls `__krepr_<T>` (Want kind 14, `key_repr_ir`) of a struct, enum, tuple or list type: a struct's `Name { f: v, … }`, an enum's `E.V` or `E.V(a, b)` (the tag compared with each variant's in turn), a tuple's `(a, b)`, a list's `[a, b]` (its packed elements read at their width), each member by its own text and a member of a compound type by its own routine (a recursive enum's box loaded first). A `char` is its code point, a `bool` `True`/`False`, a string quoted, the unit `()`, a float (in a key with a written `hash`) as the interpreter's float64, a float32 widened. Only the error's cold block calls it; the old inline text of a tuple key went into the routine, so a tuple key's site is smaller than before.

- Test first: 21 new cases in `test_runtime_errors_carry_the_interpreters_values` (struct, empty struct, unit and payload variants, a quoted string payload, tuple of struct, list, empty list, nested lists, lists of bools/chars/tuples, `Option`, a generic struct, an enum of structs and lists, a recursive enum in a struct, a `uint64` field, a unit payload, float and float32 fields, a list key of a place). Before: 18 of the first 18 failed (`map key not found`); after: all pass on x86-64, aarch64 (`MYLA_TEST_TARGET=aarch64-linux`) and wasm32 (`MYLA_TEST_TARGET=wasm32-wasi`).
- By hand, an imported type: `map key lib$Shape.Pair(lib$Q { a: 1, s: "it's" }, [1, 2]) not found` on both runners and all three targets: the interpreter's text, module ids included (see [[MYLA-514]]).
- Bootstrap fixed point: byte-identical (21,127,093 bytes).
