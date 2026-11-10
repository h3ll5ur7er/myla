---
id: MYLA-449
title: "A literal before the element that fixes a wider type must fit int32"
type: improvement
status: todo
priority: low
labels: [language, types, checker]
---
Found by the checker lane of round 5 ([[MYLA-417]]). Since L2, the literals of a list's or map's column take the type a later element fixes, each checked again against it. But each is first checked against the type the column has so far, `int32` for a first literal, so one that doesn't fit `int32` fails before the later element is seen:

```myla error
fun main() {
    let big: int64 = 5000000000
    let a = [4000000000, big]          // integer literal 4000000000 does not fit in 'int32'
    let m = [1: 4000000000, 2: big]    // the same
}
```

`[big, 4000000000]` and `let a: [int64] = [4000000000, big]` check.

- [ ] A literal that doesn't fit the column's type while only literals are in it waits for a later element's type, and the error comes at the end of the column if none fixes a type it fits (`column_step`, `close_column` in `selfhost/checker.my`)
- [ ] Error-corpus files for the error that remains, a parity program for the lists and maps that now check
