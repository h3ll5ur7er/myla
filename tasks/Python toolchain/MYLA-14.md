---
id: MYLA-14
title: Exhaustiveness check rejects exhaustive matches
type: bug
status: backlog
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

- [ ] Exhaustiveness uses a pattern-matrix algorithm (Maranget's "usefulness") that handles or-patterns, nesting, tuples and structs, and redundancy with it
- [ ] Ported to [[selfhost/checker.my]]
- [ ] Tests for both cases, plus genuinely non-exhaustive nested matches
