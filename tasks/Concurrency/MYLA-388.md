---
id: MYLA-388
title: "Inside std.task, a bare cancel(a) isn't task.cancel"
type: bug
status: backlog
priority: low
labels: [checker, concurrency]
---
Found by the channels lane ([[MYLA-351]]). The checker recognises `task.cancel` on a child task by its qualified name `std$task$cancel`, as called from another module. Inside `lib/std/task.my` itself the call is `cancel(rs)`, which isn't matched: `async let rs = all(gs)` then `cancel(rs)` fails with "'rs' is the result of a child task: read it with 'await rs'". The lane's `first` uses `__cancel_after(rs, 0)` and `__disarm`, as `timeout` does.

- [ ] The checker matches the function by what it resolves to, not by the name as written; a case in the checker and a program inside `std.task`
