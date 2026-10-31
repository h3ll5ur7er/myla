---
id: MYLA-59
title: A match ending a match-arm block must produce a value
type: bug
status: done
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

- [x] A statement match passes "no value needed" down to its arm bodies, so a trailing inner match (or `if`-less block) is checked as a statement
- [x] Test in `tests/unit/test_enums_match.py`; same fix in [[selfhost/checker.my]]

## How

A statement match passes "no value needed" to its arm bodies: the last statement of an arm block is then checked as a statement (so a `match` there is marked as a statement match, recursively), and an arm whose body is a `match` expression is marked too (`_check_arm_body(…, is_stmt)` in [[src/myla/types.py]]; `check_arm_body` / `check_arm_block` with `as_stmt` in [[selfhost/checker.my]]). The backends already generated statement-match arms as statements.

## Evidence

- `test_arm_block_of_a_statement_match_may_end_in_a_match` (the repro, prints `1 one`) and `test_a_value_match_still_needs_values` in [[tests/unit/test_enums_match.py]]. Before: `this match is used as a value, so every arm must produce one`.
- Parity program `match_statement_ending_an_arm_block` (nested statement matches in blocks and as arm bodies, and inside a value match) in [[tests/burn/test_compiler_parity.py]] and the self-hosted `PARITY_PROGRAMS`: all backends agree.

