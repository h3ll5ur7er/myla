---
id: MYLA-27
title: Const folding treats references to other consts as 0
type: bug
status: done
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

- [x] Const references fold to the referenced const's value (with cycle detection, as in `types.Checker._ensure_const`)
- [x] Unary `-`, `~` and `!` fold
- [x] Checker parity test

## How

`fold_const_expr` now ports `types.Checker._fold_const_expr`: values are kept in `const_values` and every integer result is wrapped to its node's type (so `const Z: uint8 = 128 + 128` is 0 and `1 / (Z as int)` is a const division by zero, as in Python); shifts mask the amount, `>>` and comparisons are unsigned for `uint64`, `&&`/`||` short-circuit. The self-hosted checker doesn't track float values, so a float cast to an integer folds to an unknown value and can't trigger the division check (a contrived case: `1 / (0.5 as int)`).

Tests: the parity program `consts_fold_through_references` (rejected before; both backends), checker snippets `const_division_by_wrapped_zero`, `const_division_by_negated_zero`, `const_division_through_a_const`, `const_cycle`.
