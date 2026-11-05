---
id: MYLA-279
title: "A function without a result type returns `()` (D140)"
type: feature
status: todo
priority: medium
labels: [language, types]
---
Decided by D140 (2026-11-05; changes D138): `fun f()` and `fun f() -> ()` are the same.

```myla
fun log(s: str) {
    print(s)
}

fun main() {
    let f: (str) -> () = log
    let u = f("hi")
    print(u == ())
}
```

- [ ] Checker: a function type's missing result is `()`; `return` and `return ()` the same; a call of such a function is a value of type `()` where one is wanted (`let`, an argument, `==`, a type argument: `Result<(), E>` from `Ok(f())`)
- [ ] Interpreter: its `()` and a function's "nothing" are one value (`VUnit` and the empty tuple compare equal)
- [ ] Lowering: a call without a result used as a value gives the unit value (no bytes)
- [ ] [[Language/Types]] (the unit type's last bullet), [[Language/Functions-and-closures]], the error corpus entry `type_unit_return_without_result` (no longer an error)
- [ ] Tests: interpreter and native agree, on aarch64 and wasm32 too
