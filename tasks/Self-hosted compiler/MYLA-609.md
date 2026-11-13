---
id: MYLA-609
title: "Checker: an integer literal past int32 in an if or match arm doesn't take another arm's type"
type: bug
status: todo
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

- [ ] An unsuffixed integer literal that doesn't fit `int32` in an arm of an `if` or a `match` waits for another arm's type, as one on either side of an operator does (`literal_waits` in [[selfhost/checker.my]]); with no typed arm it is the error it is today
- [ ] Cases in `selfhost/checker.my` (`errors_of`: both arm orders, `if` and `match`, negated) and the parity program of `5000000000` in an `int64` arm
- [ ] [[Language/Lexical-structure]]'s note on it removed
