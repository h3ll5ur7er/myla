---
id: MYLA-228
title: "A `yield` builtin"
type: feature
status: done
priority: low
labels: [concurrency]
---
D107 ([[MYLA-212]]): `await task.yield()` (the name the owner chose on 2026-11-02) is a suspension point that lets other ready tasks run, and where a stopped task notices the end of the program (D97). Also a cheap fix for a sibling that loops without suspending (review finding B11).

- [x] Name and place (`std.task`), in the checker, the interpreter(s) and the native runtime
- [x] A test that a spinning loop with `yield` lets a failing sibling end the program at once; [[Language/Concurrency]]

## Evidence

- **What it is.** `pub async fun yield()` in [[lib/std/task.my]] awaits the primitive `__yield()`.
  - The checker types `__yield` as a call that suspends, so it must be awaited.
  - Native code lowers `await __yield()` to the existing turn (`yield_turn`: the frame goes behind the ready ones).
  - The interpreter's primitive does nothing, and the turn after the awaited call does the rest.
  - `task.yield()` is an async function, so calling it without `await` is a type error.
- **A divergence found on the way, older than this task.** On one worker native code went on at once after awaiting an async function, method or function value that ended without suspending; the interpreter gave the other tasks a turn there. The first version of `yield` (an empty async function) showed it: the interpreter interleaved two yielding tasks and native code didn't. The interpreter now goes on at once in those cases too (`entered_async`, `calls_a_value`). Turns come after awaited actor calls and `__yield`, in both runners.
- **Test first.** `tests/burn/test_task_yield.py`:
  - A sibling spinning with `await task.yield()` lets a failing task end the program at once, in the interpreter and natively on 1 and 4 workers. On one worker the spinner runs first (depth first); without a turn it would spin for ever.
  - Two tasks yielding three times each interleave, in the same order in both runners.
  - `task.yield()` without `await` is rejected ("needs 'await'").

  Before the change the module didn't export `yield`; with the first version the turns test failed on the divergence; now all three pass.
- **Docs.** [[Language/Concurrency]] (D97's suspension points, the MYLA-170 limit and its remedy, the order of tasks), [[Language/Standard-library]], the D107 row (the name) and the myla skill. The burn suite passes (850 tests), and the bootstrap reaches its fixed point with the new seed.

