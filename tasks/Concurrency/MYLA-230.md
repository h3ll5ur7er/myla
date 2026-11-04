---
id: MYLA-230
title: "Sleep, timers, timeouts and suspending I/O on a reactor"
type: feature
status: in-progress
priority: low
labels: [concurrency, runtime, io]
---
D107 ([[MYLA-212]]): waits for the runtime off assembly ([[MYLA-162]]). A reactor (epoll on Linux) in the runtime: `sleep`, timers and timeouts on awaits, and I/O in `std.io`/`std.process` that suspends the task instead of blocking the worker.

- [x] A design after [[MYLA-162]]: the reactor's place in the executor, the platform layer's part, how the interpreters model time — D124 ([[MYLA-258]])
- [x] The clock and `sleep`: `std.time` (`now_ms`, `now_ns`), `task.sleep`, the timer heap and the poller with its event descriptor only; `exec_stuck` with timers; the interpreter's sleeping tasks (real time, `MYLA_TIME=virtual`); tests in both
- [ ] `task.timeout` and cancellation waking reactor waits
- [ ] Suspending reads on pipes and standard input
- [ ] `std.process.run` suspending, on pidfds

## Step 1: the clock and sleep (2026-11-04)

- `std.time` (`now_ns`, `now_ms`, on the primitive `__clock_ns`) and `std.task.sleep` (on the awaited primitive `__sleep`, lowered like `__yield`: the frame and a call of `myla___sleep`, then a suspension). Natively `sleep_frame` puts the frame on the timers, a heap by deadline and order under a lock; `exec_run` fires the timers that passed (queued so the earliest runs first under each order) before it looks for a frame; an idle worker that sees timers claims the poll (`__exec_polling`, one at a time) and waits in `std.platform`'s poller (epoll with an eventfd) until the nearest deadline or a push (`exec_pushed` and a new timer write the eventfd); `exec_stuck` only without timers. Without tasks `await __sleep(ms)` is the blocking `__sleep_ns`.
- The interpreter keeps its sleepers in a list: before each turn the ones whose time came are made ready (earliest first, as natively), and with no task ready it waits for the earliest, sleeping on the real clock or moving `MYLA_TIME=virtual`'s; once a task fails, every sleeper wakes so the others stop at once (D97).
- `tests/burn/test_time.py`: deadline order on 1 and 4 workers and in both orders, natively and in the interpreter on both clocks; 200 sleepers beside a computing task (all wake; in deadline order exactly with the virtual clock); a ten-second sleep in no time on the virtual clock; a failure beside a ten-second sleeper ends the program at once in both.
- On real time a sleeper whose time came while other tasks ran may go on after a later one (the newest-first order lets a later batch run before an earlier one still queued); the virtual clock orders exactly. A program with tasks that never sleeps pays one load more per frame and push: the stress programs 0.1% to 1.7% more instructions (t12, the push-heavy one, the most).

