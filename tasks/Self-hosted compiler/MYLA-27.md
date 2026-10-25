---
id: MYLA-27
title: Const folding treats references to other consts as 0
type: bug
status: backlog
priority: medium
labels: [selfhost, checker, consts]
---
In `fold_const_expr` ([[selfhost/checker.my]], around lines 2772-2777) a reference to another const folds to `0`, and unary minus is ignored.

```myla
const A: int = 4
const B: int = 100 / A
```
→ rejected as "constant division by zero" by the self-hosted checker; accepted by the Python checker.

## Done when

- [ ] Const references fold to the referenced const's value (with cycle detection, as in `types.Checker._ensure_const`)
- [ ] Unary `-`, `~` and `!` fold
- [ ] Checker parity test
