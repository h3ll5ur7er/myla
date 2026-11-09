---
id: MYLA-406
title: "A struct field and a method of the same name: the field wins silently"
type: bug
status: backlog
priority: low
labels: [language, checker, diagnostics]
---
Found by the round 3 modules lane ([[MYLA-404]]): while `Lru` had a field `keys`, `c.keys()` didn't call the method `keys` but failed on the field, with a message that didn't say why. The lane renamed the fields (`slot_keys`, `slot_vals`).

- [ ] Decide: a field and a method may not share a name (an error at the declaration, as Swift does), or a call `x.name()` resolves to the method (as Rust does)
- [ ] The checker, an error-corpus file, and [[Language/Methods-and-traits]]
