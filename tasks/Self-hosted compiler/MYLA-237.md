---
id: MYLA-237
title: "Native code takes a read-only receiver after the arguments"
type: bug
status: todo
priority: medium
labels: [backend, parity, evaluation-order]
---
Found while fixing [[MYLA-238]]. [[Language/Expressions-and-operators]] says a method call evaluates the receiver first. With a read-only `self` and an argument that changes the receiver, both interpreters take the receiver first and both native backends after the arguments:

```myla
struct C {
    n: int,
}

impl C {
    fun bump_get(var self) -> int {
        self.n = self.n + 1
        return self.n
    }
    fun plus(self, k: int) -> int {
        return self.n * 100 + k
    }
}

fun main() {
    var c = C { n: 1 }
    print(c.plus(c.bump_get()))   // interpreters: 102, native: 202
}
```

- [ ] Both backends copy (or pin) a read-only receiver's value before the arguments, as the reference says; a parity program in all four runners
