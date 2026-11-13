---
id: MYLA-586
title: Floats are Hash; hashing a NaN is a runtime error
type: feature
status: todo
priority: medium
labels: [language, stdlib, checker]
---
The owner's decision D196 (2026-11-13), superseding D163's "floats aren't `Hash`". `float32` and `float64` become `Hash`, so a float, a tuple or list of floats, an `Option<float>`, and a `#derive(Eq, Hash)` struct with float fields can be map keys and set members (points, colours, quantised coordinates in [[MYLA-587]]'s types).

- `x.hash(h)` adds the value's bits; `-0.0` and `0.0` hash alike (they are `==`), so the sign of zero is cleared first.
- Hashing a NaN is the runtime error `cannot hash NaN` (wording to settle with the message conventions), the same interpreted and natively, so a NaN never enters a map silently: it would be a key no lookup finds, as NaN is unequal to itself.
- `#derive(Hash)` accepts float fields; the hand-written workaround (`math.to_bits(x)`) keeps working.

- [ ] Tests first: a burn test with float keys (`[float: int]`, `[(float, float): str]`, a derived struct with a float field), `-0.0` and `0.0` the same key, interpreted and natively; `[panic("cannot hash NaN")]` cases; error-corpus `runtime_hash_nan.my` with its `//~ native:` line
- [ ] Checker: `primitive_default_trait` gives floats `Hash`; `validate_derive_attr`'s float refusal goes; `key_why`'s message
- [ ] `lib/std/hash.my`: `impl Hash for float64` and `float32` (the NaN check, the zero normalised); the native map routines' fast path for primitive keys, if floats join it (`key_hash_ir` in [[selfhost/lower.my]])
- [ ] Docs: [[Language/Collections-and-strings]] (map keys), [[Language/Standard-library/Hash]], the skill (`builtins.md` trait table, `SKILL.md` map keys)
- [ ] The seed: `std.hash` is implicit
