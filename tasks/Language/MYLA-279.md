---
id: MYLA-279
title: "A function without a result type returns `()` (D140)"
type: feature
status: review
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

- [x] Checker: a function type's missing result is `()`; `return` and `return ()` the same; a call of such a function is a value of type `()` where one is wanted (`let`, an argument, `==`, a type argument: `Result<(), E>` from `Ok(f())`)
- [x] Interpreter: its `()` and a function's "nothing" are one value (`VUnit` and the empty tuple compare equal)
- [x] Lowering: a call without a result used as a value gives the unit value (no bytes)
- [x] [[Language/Types]] (the unit type's last bullet), [[Language/Functions-and-closures]], the error corpus entry `type_unit_return_without_result` (no longer an error)
- [x] Tests: interpreter and native agree, on aarch64 and wasm32 too

## Built (2026-11-05)

- The checker maps a written `()` result to no result wherever a function type is made (`result_of` in `func_type`, the signatures, function types), so `fun f() -> ()`, `fun f()` and `(T) -> ()` are one thing; a call without a result where a value is wanted is `()` (`expect_value`); `return ()`, or the return of another such call, ends a function without a result.
- The lowering gives such a call an empty unit value (`addr`), and lowers `return <a () value>` in a function without a result as the value for its effects, then `return`.
- The interpreter's "nothing" (`VUnit`) and the empty tuple are one value (`value_eq`).
- [[tests/burn/test_unit_type.py]] `VOID` (also on aarch64 and wasm32, `PROGRAMS["void_is_unit"]`); `test_selfhost_checker`'s `no_value` case (`let x = print(1)`) is valid now and went; the corpus entry `type_unit_return_without_result` went too (`type_return_from_void` keeps the case that is still an error).
