---
id: MYLA-850
title: "A NaN map key's `cannot hash NaN` points into std/hash.my, not at the program's line"
type: bug
status: todo
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

- [ ] A test first: the error-corpus file `runtime_hash_nan.my` pins the program's line (`//~ native:` too), for an insert, a lookup, `contains`, a set's `insert`, and a key that holds a NaN inside a tuple or a derived struct
- [ ] The map operations report the error at their own position, interpreted and natively; `x.hash(h)` called by the program stays std.hash's
- [ ] [[Language/Standard-library/Hash]] and [[Development/Testing]]'s `test_float_keys` row (which says "at the same place in std.hash in both")

Files: the Lowering lane's [[selfhost/lower.my]] and the Interpreter lane's [[selfhost/interp.my]]; `lib/std/hash.my` perhaps not at all.
