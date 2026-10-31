---
id: MYLA-152
title: A local closure named like a builtin
type: bug
status: todo
priority: medium
labels: [selfhost, interpreter, lowering]
---
Found while triaging [[MYLA-102]], which fixed a local closure shadowing a top-level function. A local closure named like a builtin still calls the builtin in the self-hosted toolchain:

```myla
fun main() {
    let build = (n: int) => n + 1
    print(build(41))
}
```

The Python interpreter prints 42. The self-hosted `myla run` prints nothing, and the self-hosted binary segfaults. With `let len = (n: int) => n + 1` and `len(41)`, `myla run` prints `0`, and compiling fails with "main can't be lowered to the IR: the builtin len". The builtin branches in `eval_name_call` ([[selfhost/interp.my]]) and in the IR lowering ([[selfhost/lower.my]]) come before the local lookup.

- [ ] A local binding is looked up before the builtins in the self-hosted interpreter and the lowering, as in the Python interpreter
- [ ] Parity programs for a closure named like a builtin with and without a result (`build`, `len`, `print`)
