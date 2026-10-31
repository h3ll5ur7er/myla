---
id: MYLA-14
title: Exhaustiveness check rejects exhaustive matches
type: bug
status: done
priority: low
labels: [checker, match]
---
Two over-conservative cases:

1. A `bool` match only counts direct literal patterns, so `true | false` is "non-exhaustive" ([[src/myla/types.py#L2538-L2549]]).
2. A variant counts as covered only when all of its sub-patterns are irrefutable ([[src/myla/types.py#L2555-L2569]]), so nested matches are rejected:

```myla
fun f(x: Option<Result<int, str>>) -> int {
    return match x {
        Some(Ok(v)) => v
        Some(Err(e)) => 0
        None => 1
    }
}
```
→ `non-exhaustive match on 'Option': missing variant(s) Some`.

## Done when

- [x] Exhaustiveness uses a pattern-matrix algorithm (Maranget's "usefulness") that handles or-patterns, nesting, tuples and structs, and redundancy with it
- [x] Ported to [[selfhost/checker.my]]
- [x] Tests for both cases, plus genuinely non-exhaustive nested matches

## How

Maranget's usefulness algorithm in both checkers (`_useful`, `_specialize`, `_norm_pat`, `_signature` in [[src/myla/types.py]]; `useful`, `specialize`, `norm_pat`, `signature` and the `NPat` enum in [[selfhost/checker.my]]). Patterns are normalized to constructors (enum variants, `true`/`false`, the single constructor of a tuple or struct, literals keyed by value) and wildcards; or-patterns split rows. A match is exhaustive when a wildcard row isn't useful against its unguarded arms, and an arm is redundant when it isn't useful against the unguarded arms before it. The messages stay as they were where they fired before (the missing-variants list now names the variants a wildcard can still reach), and the newly found redundant arms say `unreachable match arm (earlier arms already cover it)`. `_irrefutable` is now "a wildcard isn't useful after this pattern".

## Evidence

- `TestExhaustiveness` in [[tests/unit/test_enums_match.py]]: six exhaustive matches (the two cases above, tuples and structs of `bool`, `Some(true) | None`, mixed tuples), five non-exhaustive ones with their messages, a guarded arm that doesn't cover, and six redundant arms. Before: 6 errors and 4 failures; after: all pass.
- Six new `TYPE_ERRORS` cases in [[tests/burn/test_selfhost_checker.py]] give the same verdicts in the self-hosted checker (the first port crashed with `runtime error: index out of bounds`, the message of [[MYLA-17]], on a zero-column row; fixed).
- The whole corpus (examples, stdlib, self-hosted sources) still checks; no existing code had redundant arms.

