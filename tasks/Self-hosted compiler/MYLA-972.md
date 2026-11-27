---
id: MYLA-972
title: "Interpreted `myla test`: a call in a `#test` argument that leaves out a defaulted parameter crashes the runner"
type: bug
status: todo
priority: medium
labels: [interpreter, testing]
---
Found by [[MYLA-957]]. A `#test` argument that calls a function and leaves out a parameter with a default fails the runner itself, interpreted; `--native` passes.

```myla fragment
struct Box {
    v: int,
}

fun boxed(v: int, extra: int = 0) -> Box {
    return Box { v: v + extra }
}

impl Box {
    #test(boxed(2))[2]
    fun get(self) -> int {
        return self.v
    }
}
```

`myla test` prints `runtime error: list index 1 out of bounds (len 1)` at `selfhost/interp.my:4867` (`enter_func`): the call in the attribute's argument seems to reach the interpreter without the defaults filled in (D136).

- [ ] A failing case in the test suite first
- [ ] The defaults filled in for calls inside `#test` arguments and expected values, as for calls in bodies
