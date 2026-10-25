---
id: MYLA-39
title: Rust interpreter control-flow and arity bugs
type: bug
status: backlog
priority: medium
labels: [rust, interpreter]
---
- [ ] `break`/`continue` leak out of functions: `invoke_body` and `call_closure` only catch `Return`, so a `break` in a callee ends the caller's loop
- [ ] A stray top-level `break`, or `?` returning `Err` from `main`, exits 0
- [ ] Missing arguments are filled with `Unit` and extra ones dropped; `f(1)` for `f(a, b)` fails deep inside the callee ("operator not defined for `int32` and `unit`")
- [ ] A non-`bool` `if`/`while` condition is silently false
- [ ] Errors and `return` inside `spawn` and async functions become `()` (`unwrap_or(Value::Unit)`): `spawn { panic("boom") }` awaits to `()`
- [ ] Cyclic consts (`A = B`, `B = A`) overflow the Rust stack and abort
