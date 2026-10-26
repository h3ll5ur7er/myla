---
id: MYLA-13
title: "#derive(Eq) rejects char and float fields"
type: improvement
status: review
priority: low
labels: [checker, traits]
---
`char` and the float types have built-in `==`, but the derivability check only accepts integers, `bool`, `str` and named types ([[src/myla/types.py#L1086-L1112]]).

```myla
#derive(Eq)
struct P { c: char }
```
→ `cannot derive Eq for struct 'P': field 'c' has type 'char', which is not Eq`.

## Done when

- [x] `is_eq` uses `_type_implements(t, "Eq")`, so every type with `Eq` counts (consider tuples of `Eq` types too)
- [x] Same rule in [[selfhost/checker.my]]
- [x] Test in `examples/traits.my`

## How

Both checkers count `char` and the float types as `Eq` for `#derive(Eq)` (`is_eq` in `_check_derivable_eq`, [[src/myla/types.py]]; `is_eq_type`, [[selfhost/checker.my]]). Tuples still can't be compared with `==`, so they stay out. The synthesized `eq` compares with `==`, which the interpreter and the Python backend already did correctly; the self-hosted code generator's own derived-`eq` emitter compared floats bit by bit (`NaN == NaN`, `-0.0 != 0.0`) and now uses `ucomisd` with a parity check (`emit_eq_component`, [[selfhost/codegen.my]]).

## Evidence

- Parity program `derived_eq_on_char_and_float_fields` (structs and enums, an astral `char`, NaN, `-0.0`, `float32`) in [[tests/burn/test_compiler_parity.py]] and the self-hosted `PARITY_PROGRAMS`. Before: `cannot derive Eq for struct 'P': field 'c' has type 'char', which is not Eq`; with only the checkers fixed, the self-hosted binary printed `true` for `NaN == NaN` and `false` for `-0.0 == 0.0`. After: `true false true false true true false true false` everywhere.
- `Glyph` in [[examples/traits.my]].
