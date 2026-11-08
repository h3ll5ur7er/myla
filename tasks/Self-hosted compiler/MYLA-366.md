---
id: MYLA-366
title: "Interpreter: a ? in a call's argument called the function with the arguments it had"
type: bug
status: review
priority: high
labels: [interpreter, parity]
---
Found by the stream lane ([[MYLA-338]]). `return Ok(twice(inner()?))` with `inner()` an `Err` stopped with "index out of bounds" inside the interpreter (`selfhost/interp.my:3113`); inside a `std.io` method it silently gave `Ok(empty)` instead of the `Err`. Native code returned the `Err`. `eval_name_call` (and other call sites) called `call_func(fi, self.eval_args(args))` without checking whether an argument stopped the evaluation.

- [x] `call_func`, `call_value` and `call_with_receiver` make no call when the evaluation has stopped (a deferred block clears the stop first, so unwinding is unchanged)
- [x] `test_compiler_parity`'s `try_in_a_call_argument`, interpreted and native; `test_selfhost_interp`, `test_test_functions`, `test_defer`, `test_concurrency_stress` and the interpreter's own cases (358) pass
