---
id: MYLA-818
title: "An interpreted case blocked in a system call passes its time limit"
type: bug
status: todo
priority: low
labels: [interpreter, testing]
---
Found by [[MYLA-792]] (D259). `myla test --timeout` stops an interpreted case as it runs its blocks and as its tasks wait, but not while the interpreter is inside a blocking primitive of the case's own: a child process it waits for, a blocking read of a socket. Natively the runner kills the case's process (and its process group) at the limit.

```myla fragment
import std.process as process

#test
fun starts_a_sleeper() {
    let r = process.command("sh").arg("-c").arg("sleep 300").output()
}
```

`myla test --timeout 2 t.my` waits the 300 s and then passes; `myla test --native --timeout 2 t.my` reports `FAIL  starts_a_sleeper: timed out after 2 s` after 2 s and leaves no `sleep` behind.

- [ ] The interpreter's blocking primitives that can wait without end (`__run_with`, `__reap`, a blocking read of a descriptor or a socket) wait at most until a running case's deadline (`Interp.case_deadline`), killing the child they started, and the case then times out
- [ ] A case of `tests/burn/test_test_native.py`'s `_TIMEOUT` with a child process, on both runners
