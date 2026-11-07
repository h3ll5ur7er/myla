---
id: MYLA-361
title: "myla test: a uint64 of 2^63 or more prints as negative in a failure's report"
type: bug
status: todo
priority: low
labels: [testing, printing, integers]
---
Found by the `std.hash` lane ([[MYLA-327]]). When a case fails, `myla test` reports a `uint64` of 2^63 or more as a negative number, interpreted and with `--native`. The comparison is right; `print` shows the value right. Inside a derived struct or a tuple too (`got H { s: -1 }`, `got (-1, 2)`).

```myla fragment
#test[1u64]
fun g() -> uint64 {
    return 0xFFFFFFFFFFFFFFFF
}
// FAIL  g #1: expected 1, got -1
```

- [ ] The report's value text by the value's type, unsigned as `print` does, in the interpreter's runner and the native harness
- [ ] A test of a failing case with a large `uint64`, alone and inside a struct and a tuple
