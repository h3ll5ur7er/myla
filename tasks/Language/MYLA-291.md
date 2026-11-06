---
id: MYLA-291
title: "A bound `T: Format` can't be formatted"
type: improvement
status: backlog
priority: low
labels: [checker, traits, generics]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). D139's `Format` trait is implemented for a struct and used by a format spec, but `fun show<T: Format>(x: T) -> str { return f"<{x}>" }` fails with "cannot render a value of type 'T'": D104 (6) left bounds that admit trait calls for later, so the trait's main use, a generic printer, is closed. `print(x)` also refuses a `Format` type while `print(f"{x}")` takes it.

- [ ] Bounds that admit the trait's methods and the operations the trait enables (`Format` in a hole, `Ord` in comparisons), checked at the call site as operators are
- [ ] `print(x)` of a `Format` value, or the page saying why not
