---
id: MYLA-436
title: "Interpreter: an `eq` or `hash` written for a generic type, called for a list's `==` or a map key, binds no type parameter"
type: bug
status: done
priority: low
labels: [interpreter, generics, parity]
---
Found by [[MYLA-414]]'s lane. Since MYLA-414 every generic call, operator and format binds the callee's type parameters in its frame (H1). The interpreter's own calls of a written `eq` or `hash` don't: `values_equal` comparing a list's or a struct's elements, and `key_hash`/`key_place` hashing and comparing a map's keys, call the method with no type to bind, so inside it `T` is unbound and an operation typed by `T` falls back to erasure (a `uint64` compares signed, an `int8` doesn't trap).

```myla fragment
struct W<T> {
    v: T,
}

impl<T: Ord> Eq for W<T> {
    fun eq(self, other: W<T>) -> bool {
        return !(self.v < other.v)
    }
}

fun main() {
    let x = W { v: 0u64 }
    let y = W { v: 18446744073709551615u64 }
    print(x == y)       // false on both runners: the operator binds T
    print([x] == [y])   // natively false, interpreted true: 0 < MAX read signed
}
```

- [x] `values_equal` and the map's key functions take the static type where it is known (the operator's operand, the map's or list's element type) and bind the method's frame by it (`bind_next(fi, -1, t)`), as `eval_op_overload` does; where none is known (a map's key without a type), say so here
- [x] A parity program with the reproduction

## What was built

All in [[selfhost/interp.my]]; [[Architecture/Interpreter]] describes it.

- **Every place the interpreter calls a written `eq` or `hash` itself binds the impl's type parameters**, by the static type of what it compares or hashes: `values_equal(a, b, t)` (an element's, a field's, a payload's `==` in a list's, a tuple's, a derived `eq`'s comparison), `key_hash(v, t)` and `key_place(m, k, kt)` (a map literal's keys, `m[k]` read, written or updated, `contains`, `remove`), `hash_all` (a tuple's `hash`, D163). The top type is the operand's (`full_type_of`), the map's key type (`hashed_key_type`, `index_key_type`: the map's, else, for an assignment's target, which has no type of its own, the key's) or the receiver's; a member's comes from its container's (`member_types`: a struct's fields by `struct_field_types`, an enum's payload, a tuple's elements, a list's element type). `written_eq` and `written_hash` bind by it (`bind_next(fi, -1, t)`).
- **The audit** found two more: `a.eq(b)` called on a `#derive(Eq)` type compared with `value_eq`, structurally, so a field's written `eq` was never called (`Q { a: A { v: 1 } }.eq(Q { a: A { v: 2 } })` with an `A.eq` that is always true: `false` interpreted, `true` natively), now `values_equal`; and the tuple's `hash` (`hash_all`). Not calls of user code: a `#test` case's result is compared with `value_eq`, structurally, as [[Language/Attributes-and-testing]] says; method values of a generic impl's method are refused by the checker (`cannot partially apply the generic method`). Sorting and `contains`/`index_of`/`dedup` of a list are std.list's Myla code, whose `<` and `==` on `T` already bind (MYLA-414).
- **No type known**: none is missing on these paths in a checked program (every expression has its type in `resolved`; an assignment's target `m[k]` reads its key's). A value compared or hashed without one (`t` None) binds nothing, as before.
- **The cost stays out of other programs.** `typed_keys` says whether the program has a generic struct's or enum's written `eq` or `hash` (std.hash's `impl<T: Hash> Hash for [T]` doesn't count: a list key is hashed by its elements); without one, `values_equal` and `key_hash` are the code they were (one test of a flag), and only with one `typed_equal` and `typed_hash` work out the members' types. A call by no call site (`bind_next(fi, -1, t)`, also `user_format`'s) is memoized by the function and the closed type (`type_env_memo`), where each pushed a new environment before. An argument computed by a method call inside another call made the compiled interpreter retain the map value around the call (a walk of the whole `MapV`, ~100 instructions per index), so the key types are computed into a `let` first.

## Evidence

- **Failing first**: the parity program `generic_eq_and_hash_the_interpreter_calls` ([[tests/burn/test_compiler_parity.py]]: the reproduction, the same through a struct's and an enum's derived `eq`, `Option`, a tuple, a list's `contains`, a map literal's key and `contains`, a tuple's `hash`, and a key type `K<T>` whose `eq` reads `T` and whose `hash` is constant, so that a map's lookups (`contains`, `m[k] = v`, `+=`, `get_or`, `remove`, a tuple key) compare by `eq`; and the derived `eq` called as a method) against the base interpreter (bccc624's `interp.my` in place): `false true true true true false true true true …`, `hash -1`, `1 5 5 0 true … false` where native code prints `false false … hash 18446744073709551615 … 2 5 1 1 false … true`; with this change it prints native code's output, which is pinned.
- `build/myla test selfhost/interp.my`: 434/434 (new cases: `typed_equal`, `member_types`, `payload_types`, `member_type`, `map_key_type`, `missing_key`).
- **Cost** (callgrind, instructions of `myla run`, both interpreters built by `build/myla build` from bccc624 and from this change; 20,000 iterations each): an `[int: int]` written and read 546.4 M → 549.5 M (+0.6%), a `#derive(Eq, Hash)` struct key written 448.2 M → 453.7 M (+1.2%), a derived struct's `==` 307.3 M → 307.9 M (+0.2%), `[i, 1] == [3, 1]` 230.9 M → 232.3 M (+0.6%), all four at once (15,000 iterations) 642.9 M → 649.5 M (+1.0%). The first version, with the types worked out in every program, cost +4.8% to +8.3% on these; the remainder is an `Option<Type>` argument per call.
- **Suites**: see [[MYLA-440]]'s, run on both changes together.

## Found on the way

- [[MYLA-506]]: a compound key's written `hash` runs twice per `m[k]` and `m[k] = v` interpreted (four times for `+=`), once natively.
- [[MYLA-507]]: a `#derive(Eq)` whose field's `==` needs another bound is reported at `<myla>/std/hash.my:3:23`.

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]], with a follow-up in [[MYLA-414]]: the same loss of the binding one step further: a map key's written `eq` or `hash` that runs before a `var self` call (`m[k].sort()`).
