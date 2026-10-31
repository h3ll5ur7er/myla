---
id: MYLA-149
title: Cancelling a child task by asking it
type: feature
status: done
priority: medium
labels: [concurrency, checker, runtime, selfhost, stdlib]
---
From the concurrency stress tests ([[MYLA-144]], tests 7 and 9), after [[MYLA-147]] (D94 (4): programs couldn't cancel). The user's choices: a cooperative flag, as `std.task` functions. D96.

- [x] `task.cancel(a)` and `task.cancelled()` in [[src/myla/std/task.my]]; both checkers take the call (`async let` names only, not from a lambda), error corpus cases
- [x] Both interpreters: a flag per task, seen by its children, those started later too
- [x] Native code: bit 2 of the frame flags (word 48) of the child's first frame, looked for up the chain of parents
- [x] Stress tests 7 (the resource given back at every point of cancelling) and 9 (the old request cancelled) on every implementation and on 1 to 16 workers

## Design

- **Asking.** `task.cancel(a)` sets the flag of the child task `a` and goes on: nothing waits, nothing is stopped, `await a` gives what the child returned. In the interpreters, a request sets the flag of the task and of its children; a child started later inherits its parent's. Natively, `lock or` sets bit 2 of word 48 of the child's first frame (`__task_cancel`), and `__task_cancelled` walks from the running task's first frame up through the parents (word 56); a parent outlives its children, so the walk is safe.
- **Checking.** `task.cancelled()` is a compiler builtin (`__task_cancelled`) in the library's body, so it compiles everywhere: a program without tasks gets a stub returning false.
- **Where it may stand.** The checker takes `task.cancel` as it takes `push`: its argument must be an `async let` name of the function itself (a lambda can't cancel its function's child, as it can't await it, D89). A cancel after the child's `await`, or after it ended, is harmless: its frame lives until the scope's end (where the slot is cleared; the routine leaves 0 alone).
- Considered: stopping the child at its next suspension point, as a failure does (D94). Its cleanup would need a way to run code when stopped (a `defer`), and a resource taken but not yet recorded could be lost; the flag leaves every stop to the program.

## Evidence

- Before: `task.cancel` and `task.cancelled` didn't exist (D94 (4)); test 7 couldn't be written, test 9 had only the request number.
- Before the programs synchronized, a first probe gave 1 in the Python interpreter and -1 elsewhere: the flag is checked when the child gets to it, so the stress programs pause the child at an actor gate until the parent has cancelled.
- After: `t07_cancelled_holder_gives_back`, cancelled at seven points (before taking, holding, three points of using, done using, after giving back), ends each one with the resource available and never given back twice; `t09_cancel_the_stale_request` shows "cats". Both give the same output in both interpreters and natively, with one outcome in 30 runs on each of 1, 2, 4, 8 and 16 workers.
- The two error corpus cases give the same diagnostics in both checkers (the corpus now links files that import; the self-hosted CLI compares its output with Python's).
- Unit 621, integration 2, burn 811 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (6,124,801 bytes).
