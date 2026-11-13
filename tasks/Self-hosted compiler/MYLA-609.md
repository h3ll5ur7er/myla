---
id: MYLA-609
title: "Checker: an integer literal past int32 in an if or match arm doesn't take another arm's type"
type: bug
status: review
priority: low
labels: [checker, literals, round-6]
---
Found by round 6's docs lane ([[MYLA-554]]) while checking [[Language/Lexical-structure]]'s list of where an unsuffixed literal takes its type from. [[MYLA-544]] made a literal that doesn't fit `int32` wait for the other side of an operator (`5000000000 + big`) and of a range (`big..5000000000`), and made a negated literal and a float literal take another arm's type (`if c { -1 } else { big }`). An arm's literal past `int32` still fails at once, whichever arm it is in and negated or not:

```myla error
fun main() {
    let big: int64 = 1
    let c = big > 0
    let x = if c { big } else { 5000000000 }
    print(x)
}
```

```
$ myla check a.my
type error: integer literal 5000000000 does not fit in 'int32'
  --> a.my:4:33
```

The same with `if c { 5000000000 } else { big }`, `-5000000000` in either arm, and `match c { true => big, false => 5000000000 }`. `if c { 7 } else { big }` and `if c { -1 } else { big }` are `int64`, `let x: int64 = if c { 5000000000 } else { big }` works, and so does `5000000000 + big`. Base `2ceef83`.

- [x] An unsuffixed integer literal that doesn't fit `int32` in an arm of an `if` or a `match` waits for another arm's type, as one on either side of an operator does (`literal_waits` in [[selfhost/checker.my]]); with no typed arm it is the error it is today
- [x] Cases in `selfhost/checker.my` (`errors_of`: both arm orders, `if` and `match`, negated) and the parity program of `5000000000` in an `int64` arm
- [x] [[Language/Lexical-structure]]'s note on it removed

## What changed

- `arm_literal_waits` ([[selfhost/checker.my]]): an arm's value that is an unsuffixed integer literal, negated or not, that doesn't fit `int32` (`literal_waits`), with nothing expected of the `if` or `match`, isn't inferred where the arm is checked (`check_arm_body`, and a block arm's last expression in `check_arm_block`): it is an `int32` until `unify_match_result` gives it the type of the arm that has one, as it gives a small literal or a negated one ([[MYLA-544]]). With no such arm (`if c { 1 } else { 5000000000 }`), or beside an arm of another kind (`"x"`), it is checked as before and is the error it was, at the same place; with a type expected (`let a: int32 = if …`) it doesn't wait.
- Docs: [[Language/Lexical-structure]] (the note replaced by the rule), [[Project/Known-issues]].

## Evidence

- **Tests first**, failing at `aef0b21` and passing after: `errors_of` ×6 (the `if` and `match` arms in both orders, negated, a block arm, three arms, a `uint64` past `int64`: no error, where the first was `integer literal 5000000000 does not fit in 'int32'`; and no typed arm, an `int8` arm (`does not fit in 'int8'`, was `'int32'`), a string arm and an `int32` expected: the errors they were), `arm_literal_waits` ×4. Parity program `arm_literals_past_int32` (pinned; a type error at 5:33 before): the interpreter and native code print the same, `5000000000 0 0 0`, `13000000004`, `10000000000000000000`, …
- The checker's cases: `errors_of` 101 of 101, `literal_waits` and `arm_literal_waits` 8 of 8; `scripts/test.sh fast` passes (898 tests); the bootstrap's fixed point.

