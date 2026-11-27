---
id: MYLA-850
title: "A NaN map key's `cannot hash NaN` points into std/hash.my, not at the program's line"
type: bug
status: review
priority: low
labels: [runtime, interpreter, native, stdlib, round-7]
---
Filed by [[MYLA-796]] for [[MYLA-586]]'s follow-up in [[Project/Review-2026-11-17]] (section 2): a NaN key is the runtime error D198 asks for, the same in the interpreter and natively, but its position is std.hash's `panic`, not the map operation that hashed it.

```myla fragment
fun main() {
    var m: [float: int] = [:]
    m[0.0 / 0.0] = 1
}
```

prints `runtime error: cannot hash NaN` `--> <myla>/std/hash.my:167:32` and the line of std.hash under it; a program's author wants line 3.

`#track_caller` ([[MYLA-435]]) can't stand on `impl Hash for float64`'s method (no trait-impl methods), and the call isn't the program's anyway: the map's insert or lookup hashes the key (natively `hash_key_member` in [[selfhost/lower.my]], interpreted `float_key_hash` in [[selfhost/interp.my]]). They would pass the map operation's position, as a `#track_caller` call passes its own.

- [x] A test first: the error-corpus file `runtime_hash_nan.my` pins the program's line (`//~ native:` too), for an insert, a lookup, `contains`, a set's `insert`, and a key that holds a NaN inside a tuple or a derived struct
- [x] The map operations report the error at their own position, interpreted and natively; `x.hash(h)` called by the program stays std.hash's
- [x] [[Language/Standard-library/Hash]] and [[Development/Testing]]'s `test_float_keys` row (which says "at the same place in std.hash in both")

Files: the Lowering lane's [[selfhost/lower.my]] and the Interpreter lane's [[selfhost/interp.my]]; `lib/std/hash.my` perhaps not at all.

## Evidence

Round 7's follow-ups, Numerics lane, over `3add216`. A map operation looks for a NaN in its key before it hashes it, the key itself or a member of its tuple or derived struct (as std.hash would reach it), and stops with `cannot hash NaN` at the key's position, or in a `#track_caller` function at its call's:

- natively, `Lower.nan_key_check` in [[selfhost/lower.my]], called by `key_operand`, which every map operation's key goes through (`m[k]` read and written, `m[k] op= v`, `contains`, `remove`, a literal): a load and a self-comparison per float member, `panic_term` for the position; nothing for a key type without floats, so no other program's code changes;
- interpreted, `Interp.nan_key_at` and `nan_key` in [[selfhost/interp.my]], called where those operations evaluate their key (`place_of`, `eval_index`, `contains`, `remove`, `eval_map_lit`), `failure_at` for the position;
- `#track_caller` on std.map's `get`, `get_or`, `update` and `counts` and on std.set's `of`, `insert`, `remove` and `contains`, so a NaN given to them is reported at the program's call.

A NaN inside a list or an enum key (an `Option` too), and `x.hash(h)` called by a program, still panic in std.hash's `hash`, the same in both runners: the native check would need a routine per key type to walk them.

- **The tests first**: `examples/errors/runtime_hash_nan.my` (an insert) and `runtime_hash_nan_set.my` (a set's insert of a tuple), each with its pinned `.stderr` and `//~ native:`; `tests/burn/test_float_keys.py`'s `test_a_nan_key_is_a_runtime_error_at_the_program_s_line`, 18 cases (insert, lookup, compound assignment, `contains`, `remove`, a literal, `get`, `get_or`, `update`, `counts`, a set's `insert` and `contains`, `set.of`, in a tuple, in a derived struct; and std.hash's for a list, an `Option`, a program's `hash`). Before: 15 of them failed, the error at `<myla>/std/hash.my:167:32`; after: all pass, the interpreter's and the native binary's two lines identical.
- **Suites**: `test_float_keys` and `test_float_print` on aarch64 (qemu), wasm32 (Node) and x86_64-windows (Wine) by `scripts/test-target.py`; `test_lazy_std`; `std.hash`, `std.map` and `std.set` cases interpreted and `--native`; the bootstrap's fixed point.

Functions changed in [[selfhost/interp.my]] (the Interpreter lane's): `place_of`, `eval_index`, `eval_builtin_call`'s `B_CONTAINS` and `B_REMOVE` arms, `eval_map_lit`; new `nan_key_at`, `nan_key`, `any_nan_key`. In [[selfhost/lower.my]]: `key_operand`; new `nan_key_check`.
