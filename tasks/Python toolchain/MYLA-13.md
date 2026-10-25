---
id: MYLA-13
title: "#derive(Eq) rejects char and float fields"
type: improvement
status: backlog
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

- [ ] `is_eq` uses `_type_implements(t, "Eq")`, so every type with `Eq` counts (consider tuples of `Eq` types too)
- [ ] Same rule in [[selfhost/checker.my]]
- [ ] Test in `examples/traits.my`
