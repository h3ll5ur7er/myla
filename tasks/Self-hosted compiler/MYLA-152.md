---
id: MYLA-152
title: A local closure named like a builtin
type: bug
status: review
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

- [x] A local binding is looked up before the builtins in the self-hosted interpreter and the lowering, as in the Python interpreter
- [x] Parity programs for a closure named like a builtin with and without a result (`build`, `len`, `print`)

## Evidence

- The self-hosted interpreter and the lowering look at the checker's verdict (`called_as_value`: the callee was typed as a value) before the builtins; the Python backend's pre-pass skipped indirect calls named like a builtin with a var place (`push`, `remove`, `append`), which crashed it with `AttributeError`.
- Parity program `local_closure_shadows_a_builtin` (`build`, `len`, `keys`, `push` as closures, the builtins again outside their scope): the same output from both interpreters and both backends; it is in the self-hosted gates' list too.
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
