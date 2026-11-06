---
id: MYLA-290
title: "Branches of an `if` or `match` typed against each other: `if c {{ Some(n) }} else {{ None }}`"
type: improvement
status: backlog
priority: medium
labels: [checker, inference]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). `let v = if n > 0 { Some(n) } else { None }` fails with "cannot infer type argument(s) for 'None'", as does the `match` form: the arms are typed one by one, so a bare `None` or `[]` in one arm can't take its type from another or from the binding's annotation. It is the first `if` expression people write.

- [ ] An arm without a type of its own takes the type of the first arm that has one, or the expected type; both checkers (one now) and the interpreter agree
- [ ] A burn test with `Some`/`None`, `[]`, `Ok`/`Err` across arms
