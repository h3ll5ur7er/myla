---
id: MYLA-150
title: Concurrency follow-ups - failures end the program at once, task.cancel only called
type: feature
status: in-progress
priority: medium
labels: [concurrency, checker, runtime, selfhost]
---
After [[MYLA-149]]: the follow-ups to the concurrency work ([[MYLA-61]]). The user's decision: a child's failure reaches its parent at once, for every child (D97).

- [x] `task.cancel` used as a value is an error in both checkers (it did nothing), with an error corpus case
- [x] A failure in any task ends the program at once, in both interpreters and natively (D97): the parent no longer waits for a looping child it awaits first, nor `task.all` for its first function
- [x] Stress programs for both hangs; the tests that pinned D89's held failures updated
- [ ] Actor-heavy programs on more workers: measured, and improved if a cheap change helps

## Design

- **Why one flag.** A failure can't be caught, so it always ended the program, only late: once its parent awaited the failing child or ended its scope. Reaching the parent at once, then its parent, and so on, ends at the entry, so the whole program stops: the first failure claims the program, every other task stops at its next suspension point (D94 (2)), and the entry reports it.
- **Python interpreter.** `_failing` (under a lock) holds the first failure of a task thread; at a suspension point, a task thread stops (`_Cancelled`) and the main thread raises it. A scope's end, after waiting for its children, is a suspension point too.
- **Self-hosted interpreter.** `end_task` of a failing task (not a cancelled one's stop) records the failure and cancels the first task, so every task; the first task, when it next runs, stops with that failure instead of silently.
- **Native code.** `__task_fail` claims `__exec_failing` with `lock cmpxchg`; the executor drops every frame it takes once the flag is set (one `cmp` where D94 walked the task's parents), and the claimant waits until no other worker runs a frame (`__wait_stopped`), then reports and exits. A later failure goes back to the executor. Tasks no longer end failed, so the failure words of a task's first frame, the "children cancelled" flag and `__task_check` are gone.

## Evidence
