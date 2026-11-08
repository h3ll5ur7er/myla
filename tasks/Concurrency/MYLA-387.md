---
id: MYLA-387
title: "A runtime primitive to park a task until it is woken"
type: feature
status: review
priority: medium
labels: [runtime, concurrency, primitives]
---
Found by the channels lane ([[MYLA-351]]). No primitive parks a task until a condition holds, so a waiting `send`, `recv` or `task.first` looks again: 32 turns, then sleeps of 1, 2 and 4 ms. That costs about 240 ms of CPU for eight tasks idle 2 s on four workers, wakes 1–3 ms late, and caps a channel at about 600,000 messages a second on four workers (3.1 M on one).

- [x] A park and a wake primitive (a wait queue an actor's method can hold, or a "notify" handle), in `std.rt`'s executor and the interpreter's scheduler, natively on every target; cancellation (D96) ends a park
- [x] `std.task`'s channels, pool and `first` on it, measured against the polling version (the channels lane's, [[MYLA-351]]: its `pause` loop gives way to a notifier)

## The design

A **notifier** (`std.task.notifier()`, [[Language/Concurrency#Waiting until woken]], [[Language/Standard-library/Task#Notifiers]]) is a handle, a struct holding one `int64`: a copy reaches the same notifier, as an actor's handle does, so it crosses tasks and actor calls as a deep copy for free, and an actor's method can keep the notifiers of the tasks waiting for it in its fields and wake them. That fits Myla's value semantics without a new reference type, and makes the channel's way race-free: a receiver that finds the queue empty leaves its notifier with the actor in the same call (look and register are one step), and the send's call wakes it.

- `n.notify_one()`: wakes the oldest waiter, or leaves a **counted permit** that the next wait takes at once. Every `notify_one` ends exactly one wait, so a wake before the wait is never lost, also with several waiters on one notifier (a single permit would lose the second of two wakes).
- `n.notify_all()`: wakes every waiter parked now, leaves no permit, and counts a **generation**; `n.listen()` gives a `Listener` from now on whose `wait`/`wait_timeout` also end at once when a `notify_all` came since, so a broadcast between looking at a condition and waiting isn't missed (the barrier in t28).
- `await n.wait() -> bool`, `await n.wait_timeout(ms) -> bool` (also on a `Listener`): `true` when woken; `false` when the time passed or the task was asked to stop. `ms <= 0` doesn't wait (a try).
- Cancellation (D96) ends a parked wait at once (and a wait started after it doesn't wait); the task sees `task.cancelled()`. A failure (D97) ends the program: natively parked frames are never resumed; the interpreter wakes every parked wait, which then stops.
- Stuck detection: a parked task without a time limit isn't a timer or a watch, so when every worker is idle with nothing queued, `exec_stuck` reports `every task waits for another one` (status 1); a wait with a time limit is a timer, so it isn't stuck. The interpreter now reports the same when its loop ends with the first task not done (it had no such report: nothing could deadlock before).

**Primitives** (`is_notify_primitive` in [[selfhost/checker.my]]): `__notifier()`, `__notify(n, all)`, `__notify_gen(n)`, `__waiter(n, since, ms)`, `await __park(w)` (suspends, lowered like `__wait_socket`: `std.rt.park_frame(frame, w)` then `Term.Suspend`), `__woken(w)`. Natively each is a function of `std.rt` ([[lib/std/rt.my]], "notifiers"): a notifier is a record `[permits][generation][first][last]` (never freed), a wait a waiter cell `[frame][notifier][next][prev][next parked][prev parked][state][since][ms]` freed by `__woken`. Everything is under the timers' lock, since a time limit is a timer (the waiter tagged 2) and a cancel already runs under it: `cancel_locked` walks `__parked`, the one new runtime variable, `timers_fire` ends a timed-out wait, `notify` and the cancel take the timer off. Without tasks `__park` and `__notify` become `park_alone`/`notify_alone` (no one else can wake: at once, after the time limit, or stuck). The interpreter ([[selfhost/interp.my]], "notifiers") keeps `Notif`s and `PWait`s, a wait's time limit a `Sleeper` with a `wait`, and wakes in native code's order (an immediate wait is queued, `notify_all` queues the oldest waiter to run first, fifo too), so one worker prints what the interpreter prints in every `MYLA_SCHED` order.

**Seed (D156):** no staging. The seed compiles the new compiler from the new `lib/std/rt.my` without knowing any of this: the compiler itself has no tasks, so the executor's functions, the only ones that name `__parked`, aren't compiled into it, and the new primitives are only compiled when a program calls them. `scripts/bootstrap.sh` from the old seed reaches the byte-identical fixed point.

## Evidence (2026-11-08)

- **Before:** on b977e50 `std.task` has no `notifier`, so the new parity programs, t28, t29 and the `#test` functions can't check; the tests were written against the API and run to green.
- **Bootstrap:** byte-identical fixed point from the unchanged seed (17,171,004 bytes).
- **Tests:**
  - six parity programs (`notifier_ping_pong`, `notifier_notify_all`, `notifier_wake_before_wait`, `notifier_cancelled_waiter`, `notifier_timed_out_wait`, `notifier_wakes_a_receiver`): native = interpreter = the pinned output, on x86-64, aarch64 (qemu) and wasm32 (node);
  - stress programs `t28_parked_and_woken` (8 ping-pong pairs × 1,000 rounds, a ring of 16 × 200 laps, a 16-task barrier × 100 rounds through `listen`/`notify_all`) and `t29_nobody_left_to_wake`, interpreted and natively on 1, 4 and 16 workers (3 runs each) and in the fifo and seed orders on one worker; `test_what_they_report` checks t29's message interpreted and on 1 and 4 workers;
  - five `#test` functions and `limit`'s three cases in `std.task`, interpreted, `--native` and `--target aarch64-linux`;
  - a program printing the wake order matched the interpreter on one worker in the default, fifo, seed:1, seed:2 and seed:7 orders;
  - the no-tasks lowering (`park_alone`, `notify_alone`) by a program on the primitives: same output interpreted, natively, on aarch64 and wasm32.
  - suites: `scripts/test.sh fast` 689 tests OK (2 skipped); `test_compiler_parity`, `test_concurrency_stress`, `test_selfhost_cases`, `test_time`, `test_task_yield`, `test_std_modules` 227 tests OK; `scripts/test-target.py aarch64-linux test_compiler_parity` and `wasm32-wasi test_compiler_parity` OK; `test_doc_blocks` OK (the new pages' programs run).
- **Measurements** (x86-64, 4 CPUs, native):
  - ping-pong through two notifiers, 1,000,000 round trips: 4.8 M round trips/s on 1 worker, 0.42–0.43 M on 4 (the woken frame is usually stolen by an idle worker: each hand-off crosses cores; 7 s user over 2.4 s);
  - eight tasks parked 2 s, then `notify_all`: 0.000–0.001 s user+sys on 1 and 4 workers (polling: 50 ms on one, 240 ms on four);
  - an unbounded actor queue whose empty `take` registers the receiver's notifier: 6.0 M messages/s on 1 worker, 1.4 M on 4 (MYLA-351's polling bounded channel: 3.1 M and 0.6 M).

- **Channels, `pool` and `first` on notifiers** ([[MYLA-351]], redone on `3f1487e`). A channel is a generic actor whose waiters park on one notifier each, served directly by the other side; a wait that gives up after it was served takes its outcome. `first` waits on a channel, and `pool` never polled. Measured against the polling version on the same machine, natively, best of 5: a channel of 16 between two tasks carries 3.30 M msg/s on 1 worker and 721,000 on 4 (8 producers and 8 consumers over 256: 968,000) (polling: 3.09 M, 472,000 and 771,000). Eight tasks idle 2 s on empty channels take 0 to 1 ms of CPU (polling: 52 and 213 ms), and a parked receiver wakes in 3 µs on 1 worker and 15 µs on 4 (polling: 1.3 to 2.2 ms). Stress programs t31 to t34.

## Not done

- On several workers a hand-off between two tasks moves the woken task to another worker most of the time (the executor's stealing, not the notifier); a "run the woken task next on this worker" policy would help ping-pong.
- A partial deadlock (some tasks waiting on each other while others run) isn't detected.
- Found by [[MYLA-351]]: on several workers, more than one idle worker can see every task waiting, and each `exec_stuck` writes `every task waits for another one` before the exit, so stderr may hold the line twice. That happened in 5 of 80 runs of t29 on 4 and 16 workers. A minimal case is 64 tasks that `await task.yield()` and then `await n.wait()` on one notifier, under `task.all`, on 16 workers (2 of 60 runs). `test_what_they_report` can fail by chance on 4 workers for this reason. A fix: claim the report (an exchange on a flag) before writing it.
