---
id: MYLA-39
title: Rust interpreter control-flow and arity bugs
type: bug
status: done
priority: medium
labels: [rust, interpreter]
---
- [ ] `break`/`continue` leak out of functions: `invoke_body` and `call_closure` only catch `Return`, so a `break` in a callee ends the caller's loop (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] A stray top-level `break`, or `?` returning `Err` from `main`, exits 0 (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] Missing arguments are filled with `Unit` and extra ones dropped; `f(1)` for `f(a, b)` fails deep inside the callee ("operator not defined for `int32` and `unit`") (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] A non-`bool` `if`/`while` condition is silently false (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] Errors and `return` inside `spawn` and async functions become `()` (`unwrap_or(Value::Unit)`): `spawn { panic("boom") }` awaits to `()` (dropped: the Rust edition was removed, [[MYLA-70]])
- [ ] Cyclic consts (`A = B`, `B = A`) overflow the Rust stack and abort (dropped: the Rust edition was removed, [[MYLA-70]])

**Closed without a fix:** the Rust edition was removed from the repository ([[MYLA-70]]); its code is in git history (commit `043acb9`). See [[Architecture/Rust-edition]].
