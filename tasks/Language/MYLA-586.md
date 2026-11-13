---
id: MYLA-586
title: Floats are Hash; hashing a NaN is a runtime error
type: feature
status: review
priority: medium
labels: [language, stdlib, checker]
---
The owner's decision D196 (2026-11-13), superseding D163's "floats aren't `Hash`". `float32` and `float64` become `Hash`, so a float, a tuple or list of floats, an `Option<float>`, and a `#derive(Eq, Hash)` struct with float fields can be map keys and set members (points, colours, quantised coordinates in [[MYLA-587]]'s types).

- `x.hash(h)` adds the value's bits; `-0.0` and `0.0` hash alike (they are `==`), so the sign of zero is cleared first.
- Hashing a NaN is the runtime error `cannot hash NaN` (wording to settle with the message conventions), the same interpreted and natively, so a NaN never enters a map silently: it would be a key no lookup finds, as NaN is unequal to itself.
- `#derive(Hash)` accepts float fields; the hand-written workaround (`math.to_bits(x)`) keeps working.

- [x] Tests first: a burn test with float keys (`[float: int]`, `[(float, float): str]`, a derived struct with a float field), `-0.0` and `0.0` the same key, interpreted and natively; `[panic("cannot hash NaN")]` cases; error-corpus `runtime_hash_nan.my` with its `//~ native:` line
- [x] Checker: `primitive_default_trait` gives floats `Hash`; `validate_derive_attr`'s float refusal goes; `key_why`'s message
- [x] `lib/std/hash.my`: `impl Hash for float64` and `float32` (the NaN check, the zero normalised); floats don't join the primitive fast path: natively `hash_key_member` ([[selfhost/lower.my]]) calls `float64.hash` for a float member, and the interpreter's `float_key_hash` calls it for a NaN, so the error is raised at the same place in std.hash by both
- [x] Docs: [[Language/Collections-and-strings]] (map keys), [[Language/Standard-library/Hash]], the skill (`builtins.md` trait table, `SKILL.md` map keys)
- [x] The seed: `std.hash` is implicit

## Evidence

- `primitive_default_trait` and `is_hash_type` make floats `Hash`; the explanations of D163's refusal (`float_note`, `holds_float`, "NaN is unequal to itself") are gone, their checker cases now assert that `[(int, float): int]` and `#derive(Eq, Hash) struct P { x: float }` check.
- Hashing: std.hash's `float64.hash` adds the bits of the value with `-0.0` as `0.0` and panics `cannot hash NaN` for a NaN; native map routines call it for every float member of a key (a float32 widened first); the interpreter hashes a float by its bits (`value_hash`, `-0.0` folded) and calls the same `hash` for a NaN. Key equality was already by value in both.
- Tests: `tests/burn/test_float_keys.py` 2/2 (float, tuple, list, `Option`, `float32` and derived-struct keys, `-0.0`/`0.0` one key, alike interpreted, natively and as wasm32; a NaN key is `runtime error: cannot hash NaN` at `std/hash.my:167:32` in both). std.hash's cases 68/68 interpreted and `--native`; checker 1018/1018, interp 447/447, lower 150/150.
- Docs: [[Language/Collections-and-strings]], [[Language/Standard-library/Hash]], [[Language/Methods-and-traits]], [[Development/Testing]], the skill.
