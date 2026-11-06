---
id: MYLA-290
title: "Branches of an `if` or `match` typed against each other: `if c {{ Some(n) }} else {{ None }}`"
type: improvement
status: review
priority: medium
labels: [checker, inference]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). `let v = if n > 0 { Some(n) } else { None }` fails with "cannot infer type argument(s) for 'None'", as does the `match` form: the arms are typed one by one, so a bare `None` or `[]` in one arm can't take its type from another or from the binding's annotation. It is the first `if` expression people write.

- [x] An arm without a type of its own takes the type of the first arm that has one, or the expected type; both checkers (one now) and the interpreter agree
- [x] A burn test with `Some`/`None`, `[]`, `Ok`/`Err` across arms

## Evidence

- `infer_match` in [[selfhost/checker.my]] (an `if` is checked as a match) finds, when nothing is expected, the arms whose value can't give its type alone (`arm_needs_context`: `None`, `[]`, `[:]`, `Ok`/`Err`, a generic enum's variant whose payload leaves a type parameter out (`variant_leaves_params`), an inner `if` or `match` all of whose arms can't), checks the others first and these with the first one's type expected. Arms keep their order for the result and its messages. The interpreter and the backends take the types the checker resolved, so they agree by construction; the language server uses the same checker.
- `test_a_branch_takes_its_type_from_another` in `tests/burn/test_if_expression.py`: `Some`/`None` both ways round, `[]` in a `match`, `[:]`, an `else if` chain, `Err` beside a call returning `Result`, a user generic enum, in the interpreter and natively. It failed before ("cannot infer type argument(s) for 'None'"), and passes now. Two branches that each leave a parameter open (`Ok(1)` and `Err("e")`) still need an annotation (the same test), as [[Language/Generics]] says.
