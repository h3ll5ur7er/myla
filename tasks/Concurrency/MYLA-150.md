---
id: MYLA-150
title: Concurrency follow-ups - failures end the program at once, task.cancel only called
type: feature
status: done
priority: medium
labels: [concurrency, checker, runtime, selfhost]
---
After [[MYLA-149]]: the follow-ups to the concurrency work ([[MYLA-61]]). The user's decision: a child's failure reaches its parent at once, for every child (D97).

- [x] `task.cancel` used as a value is an error in both checkers (it did nothing), with an error corpus case
- [x] A failure in any task ends the program at once, in both interpreters and natively (D97): the parent no longer waits for a looping child it awaits first, nor `task.all` for its first function
- [x] Stress programs for both hangs; the tests that pinned D89's held failures updated
- [x] Actor-heavy programs on more workers: measured, and improved if a cheap change helps

## Design

- **Why one flag.** A failure can't be caught, so it always ended the program, only late: once its parent awaited the failing child or ended its scope. Reaching the parent at once, then its parent, and so on, ends at the entry, so the whole program stops: the first failure claims the program, every other task stops at its next suspension point (D94 (2)), and the entry reports it.
- **Python interpreter.** `_failing` (under a lock) holds the first failure of a task thread; at a suspension point, a task thread stops (`_Cancelled`) and the main thread raises it. A scope's end, after waiting for its children, is a suspension point too.
- **Self-hosted interpreter.** `end_task` of a failing task (not a cancelled one's stop) records the failure and cancels the first task, so every task; the first task, when it next runs, stops with that failure instead of silently.
- **Native code.** `__task_fail` claims `__exec_failing` with `lock cmpxchg`; the executor drops every frame it takes once the flag is set (one `cmp` where D94 walked the task's parents), and the claimant waits until no other worker runs a frame (`__wait_stopped`), then reports and exits. A later failure goes back to the executor. Tasks no longer end failed, so the failure words of a task's first frame, the "children cancelled" flag and `__task_check` are gone.
- **A busy actor.** Eight tasks calling one actor ran 9 to 13 times slower on 2 to 4 workers than on one, with only 7 `futex` calls (no sleeping): a frame finding the actor busy queues and is later handed it, keeping it while it waits in a run queue, so every caller after it queues too (a convoy), and every call costs a queueing and a hand-off. Without the yield after each call it was a little faster; a shorter idle spin changed nothing. On more than one worker, a frame finding the actor busy with no frame queued now waits up to 1,000 `pause`s for it before queueing; no one waits before it, so callers are still served in order, and one worker never waits (the holder couldn't leave meanwhile, and the order stays the self-hosted interpreter's).

## Evidence

- Before (merged master): the Python interpreter waited for ever (killed after 15 s) on a parent awaiting a looping child while its second child failed, and on `task.all` whose last function failed while its first looped. After: both end at once with the failure's message and place, exit 1, in both interpreters and natively on 1 and 4 workers (`t08_failure_reaches_a_waiting_parent`, `t08_group_fails_fast`).
- `t08_failing_child_cancels_its_children` no longer prints "main still runs": the entry stops at its next call of the actor. The native held-failure test is now `test_child_failures_end_the_program_at_once`; its outputs (one worker) are the self-hosted interpreter's.
- `let stop = task.cancel` is rejected by both checkers with the same message (`type_task_cancel_as_value`).
- Eight tasks making 20,000 calls each of one actor (median of 9 runs): 17, 118, 189, 253 ms on 1, 2, 4, 8 workers before, 14, 49, 80, 103 ms after.
- Unit 621, integration 2, burn 812 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (6,119,865 bytes).
