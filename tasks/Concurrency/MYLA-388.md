---
id: MYLA-388
title: "Inside std.task, a bare cancel(a) isn't task.cancel"
type: bug
status: review
priority: low
labels: [checker, concurrency]
---
Found by the channels lane ([[MYLA-351]]). The checker recognises `task.cancel` on a child task by its qualified name `std$task$cancel`, as called from another module. Inside `lib/std/task.my` itself the call is `cancel(rs)`, which isn't matched: `async let rs = all(gs)` then `cancel(rs)` fails with "'rs' is the result of a child task: read it with 'await rs'". The lane's `first` uses `__cancel_after(rs, 0)` and `__disarm`, as `timeout` does.

- [x] The checker matches the function by what it resolves to, not by the name as written; a case in the checker and a program inside `std.task`

## Evidence

- Cause: from another module the loader names std.task's function `std$task$cancel`, but in `lib/std/task.my` checked as the entry file (`myla test lib/std/task.my`, where its `#test` functions run) the names stay unqualified, so `cancel(rs)` didn't match.
- Now the checker takes `task.cancel` by what the name resolves to (`is_task_cancel`): `std$task$cancel`, or a function `cancel` whose declaration's origin is std.task. When the entry file is a module of `std`, the loader records its functions' origins in `Loaded.std_impls` with the module's dotted name (`std_module_name`, [[selfhost/loader.my]]); the checker records such a callee in `renames`, and `fill_in` gives it the qualified name, which the interpreter and the lowering already take.
- Before: with `first`'s `__cancel_after(rs, 0)` … `__disarm(t)` written `cancel(rs)`, `myla check lib/std/task.my` gave "'rs' is the result of a child task: read it with 'await rs'". After: `std.task`'s `first` and its test `cancelled_waits` use `cancel` (the workaround's only other use, `timeout`, needs its deadline and keeps `__cancel_after`); `myla test lib/std/task.my` 31/31, interpreted (embedded library and `MYLA_STDLIB=lib`), natively, and `--target aarch64-linux` for `the_first`; a program importing std.task that cancels a child still prints what it did.
- Cases: `Checker.is_task_cancel` (a program's own `cancel` isn't, `std$task$cancel` is), `std_module_name` in the loader.

Suites at the batch's tip: the bootstrap's fixed point; `scripts/test.sh fast` 714 OK (with the embedded library regenerated); `tests.burn.test_compiler_parity`, `test_selfhost_cases`, `test_error_corpus`, `test_selfhost_checker`, `test_lsp`: 673 OK.
