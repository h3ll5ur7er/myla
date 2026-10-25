---
id: MYLA-59
title: A match ending a match-arm block must produce a value
type: bug
status: backlog
priority: low
labels: [checker, match]
---
When a block arm ends with a `match`, the checker treats that inner `match` as the arm's value, even when the outer `match` is a statement and needs no value.

## Steps to reproduce

```myla
fun main() {
    let r: Result<int, str> = Ok(1)
    match r {
        Ok(n) => {
            print(n)
            match n {
                1 => print("one")
                _ => print("other")
            }
        }
        Err(e) => print(e)
    }
}
```

## Expected

Prints `1` and `one`.

## Actual

`type error: this match is used as a value, so every arm must produce one`. `_check_arm_body` infers the last expression statement as the arm's value without knowing whether the outer match is a statement ([[src/myla/types.py#L2316-L2334]]).

## Done when

- [ ] A statement match passes "no value needed" down to its arm bodies, so a trailing inner match (or `if`-less block) is checked as a statement
- [ ] Test in `tests/unit/test_enums_match.py`; same fix in [[selfhost/checker.my]]
