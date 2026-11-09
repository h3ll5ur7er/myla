---
id: MYLA-351
title: "std.task: channels, pools and timeouts"
type: feature
status: review
priority: low
labels: [stdlib, concurrency, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #66. Built on actors and the reactor ([[Language/Concurrency]]).

- **Owns:** `lib/std/task.my` (additions), `docs/Language/Standard-library/Task.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Channel<T>` between tasks, bounded and unbounded
- [x] A worker pool
- [x] A timeout around any await and waiting for the first of several
- [x] The concurrency stress tests extended to them ([[Development/Concurrency-stress-tests]])
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

Redone on `3f1487e` (master after wave 4 part 1, with [[MYLA-386]]'s generic actors and [[MYLA-387]]'s notifiers). The first attempt (branch `myla-351-polling`, `ae10398`) made each program declare an actor per element type and had every wait look again (32 turns, then sleeps of 1, 2 and 4 ms); the owner set it aside for these two features. Its buffer rules, tests and stress programs were reused where they still applied. The page is [[Language/Standard-library/Task]].

**What was built** ([[lib/std/task.my]]):

- **Channels.** `channel<T>(cap: int) -> Channel<T>` (at most `cap` values; 0, or less, a rendezvous) and `unbounded<T>() -> Channel<T>`, of any `T`, with no actor or closure from the program: `let ch: task.Channel<int> = task.channel(4)`, or `task.channel<int>(4)`. The names: `channel(cap)` is the channel most programs want, a bounded one, as Go's `make(chan T, cap)` with 0 the rendezvous; an unbounded channel has no back-pressure, so it gets a name of its own rather than a magic capacity. `Channel<T>` is a struct holding the handle of a private generic actor, `Queue<T>`, so its methods are the waits and the actor's methods the single steps. Its methods (async): `send`, `recv` (`None` once closed and drained, or cancelled while waiting), `try_send`, `try_recv`, `send_timeout`, `recv_timeout`, `close`, `len`. `ChannelError` (D168) is `Closed`, `Full`, `Empty`, `TimedOut`, `Cancelled`, with `message()` and `Format` (the spec ignored, as most modules' errors do).
- **Waits park, with no polling anywhere.** The actor holds the values and the waiting senders and receivers, oldest first. A step that can't go on registers its task in the same call, in a slot with a notifier of its own, and the task parks on it. The other side's step serves the oldest waiter directly: a send hands its value to a waiting receiver, a receive moves the oldest waiting sender's value into the room it made (on a rendezvous, takes it), `close` serves every waiter with `Closed`. The outcome stays in the slot until the woken task takes it (`settle`).
- **The give-up race** ([[MYLA-387]]'s note). A wait that ends without a wake (time limit, cancel) settles with `stop`. Still registered, the waiter is taken off (an entry with an older `seq` is skipped later), and a sender's value is taken back. Already served, it takes the outcome: a value handed to a receiver as it gave up is still that receiver's, so no value sits unseen and no other waiter's wake is lost. Nothing has to be passed on, since each waiter has its own notifier and its own outcome. The late wake stays on the slot's notifier as a permit; the slot's next waiter gets one early wake, `settle` says `Pending`, and it waits again. Slots and their notifiers are reused (a notifier is never freed natively), so a channel makes as many notifiers as it ever had waiters at once. The entries of waiters that gave up are dropped lazily, and a waiters' queue holding more than twice as many entries as there are slots in use is compacted, so a receiver timing out over and over on a quiet channel doesn't make it grow (a test: 1,000 give-ups behind one patient waiter leave fewer than 40 entries; it failed before the compaction).
- **Pools.** `pool(n, jobs, f) -> [R]`, results in the order of `jobs`; its workers take indices from a small actor, a plain awaited call that never polled. `workers(n, jobs, results, f) -> int` runs over channels, so its waits park.
- **The first of several.** `first(fs) -> Option<(int, T)>`: each function sends its index to an unbounded channel when it has finished, and `first` waits on that channel's `recv`, then cancels and awaits the rest. The first attempt looked at an actor again and again. `timeout` already wrapped any await.
- `std.deque` is no longer imported: a private `Fifo<T>` (a list and a head index, compacted once half is taken) saves every importer 2.3 ms of checking.

**Tests first.** The test functions and the stress programs were written against the new API and failed (`type 'Step' is not generic`, no `Channel`), then went green. Two mutants fail them. A queue that ignores `seq`, serving a waiter that gave up, fails `the_steps`, `timing_out` and `cancelled_waits`. A `settle` that drops a served outcome when its wait gave up (the race) fails `the_steps`, and t33 natively in 25 of 28 runs ("timing out receivers, every value once false").

- `build/myla test lib/std/task.my --stdlib lib`: 31/31. That is 13 `#test` cases (`ChannelError.message` ×5, `format`, `limit` ×3, `said` ×2, `slot_of` ×2) and 18 test functions (5 of them MYLA-387's notifier tests). Among the test functions: `the_steps` and `the_steps_of_a_rendezvous` drive the actor's steps one at a time, the give-up race and a reused slot's early wake among them; `any_element_type` covers `str`, `[int]` and a struct; `woken_in_time` and `cancelled_waits` are new. All pass interpreted (also `MYLA_TIME=virtual`, `MYLA_SCHED=fifo`, `seed:1`, `seed:2`), `--native` (default, `MYLA_THREADS=1`, `16`), `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (node): 31/31 each.
- Stress programs ([[Development/Concurrency-stress-tests]]); the first attempt's t28 to t30 are renumbered, since MYLA-386 and MYLA-387 took those numbers:
  - `t05_channels_wait_for_each_other`: the plan's example 5. Both rendezvous sends time out and their values are taken back; in the other order the exchange goes through.
  - `t31_channel_many_to_many`: 8 producers and 8 consumers over capacities 4, 0 and unbounded, and a channel of `str`. 3,200 values each, every one received once.
  - `t32_channel_cancelled_midway`: a consumer and a producer cancelled once a quarter went through. What was sent is received once, by a consumer or the drain.
  - `t33_pools_and_the_first`: pool order; a cancelled `workers`, every job done once or left; receivers timing out over and over; new: senders timing out over and over on a rendezvous and on a channel of 2 while consumers pause, where exactly the values whose send gave `Ok` are received, once; `first` of 16.
  - `t34_channels_nobody_left` (new): 100 receivers parked and woken, a sender waiting for room, then every task waiting on a channel. It ends with `every task waits for another one` (status 1), which a polling wait never would.

  All give the same output interpreted and natively: 470 native runs of the five (30 each on 2, 4 and 16 workers, and the four orders on one) with 0 mismatches.
- Suites, after `scripts/bootstrap.sh`: `scripts/test.sh fast` 695 tests OK (2 skipped); `test_concurrency_stress`, `test_compiler_parity`, `test_std_modules`, `test_doc_blocks`, `test_time`, `test_task_yield`: 235 tests OK; `test_aarch64.Aarch64Tasks` (every stress program under qemu on 1, 4 and 16 workers and in the four orders) and `test_wasm.WasmTasks` (on node, in each order; t27 skipped, WASI has no child processes): OK.

**Measured** natively (x86-64, 4 cores), best of 5, 400,000 messages. The polling version is the first attempt's `task.my` in a copy of `lib/`, measured on the same machine; its numbers match those it recorded (3.14 M and 555,000 msg/s).

| msg/s | 1 worker, parked | 1 worker, polling | 4 workers, parked | 4 workers, polling |
| --- | --- | --- | --- | --- |
| capacity 16, two tasks | 3.30 M | 3.09 M | 721,000 | 472,000 |
| capacity 16, 8 producers and 8 consumers | 3.27 M | 3.13 M | 862,000 | 805,000 |
| capacity 1, two tasks | 3.26 M | 3.15 M | 566,000 | 361,000 |
| capacity 256, 8 and 8 | 3.27 M | 3.11 M | 968,000 | 771,000 |
| rendezvous, two tasks | 1.87 M | 1.37 M | 365,000 | 106,000 |

- Idle: eight tasks waiting 2 s on empty channels take 0 ms of CPU on 1 worker and 1 ms on 4. Polling took 52 ms and 213 ms.
- Wake latency: a receiver parked on a channel, the sender sending its clock reading every 10 to 16 ms. Parked: median 3 µs (max 5 to 35) on 1 worker, 15 µs (max 35 to 139) on 4. Polling: median 1.3 to 2.2 ms, max 4.2 ms.
- Check time of `import std.task` in a program printing 1, best of 9: base (`3f1487e`) +0.9 ms, polling +10.6 ms, this +10.5 ms (59.3 against 48.8 ms); +10.2 against polling's +10.9 after the last change (the pruning below), measured with a suite running alongside. On the way it was +14.8 ms: `std.deque` cost about 2.5 ms (now a private `Fifo`), `pad` 1.6 ms (now `format` gives the message). The module's own test functions are checked for every importer too: about 6 ms of the 10.5.
- A first version was slower than polling on one worker (2.7 M msg/s). The fast path went through one more async function (`settled`) and looked at empty waiter queues; both were taken out (3.3 M). The 4-worker numbers vary by about 10 % between runs of five.

**The bootstrap (D156).** The compiler doesn't import `std.task`; it only names `std$task$cancel` and the primitives. So neither generic actors nor notifiers reach the seed, and `scripts/bootstrap.sh` from the unchanged seed reaches the byte-identical fixed point (17,344,095 bytes). The new `selfhost/embedded_std.my` is left for the integrator's seed commit.

**Found on the way.**

- *Runtime, MYLA-387:* when every task waits, more than one idle worker can report it. `exec_idle` calls `exec_stuck` in each worker that sees `exec_all_waiting()`, and `exec_stuck` writes the message and exits without claiming the report first, so stderr holds the line twice (once three times). It shows on t29 (5 of 80 runs on 4 and 16 workers) and t34 (19 of 80). A minimal program: 64 tasks that `await task.yield()` and then `await n.wait()` on one notifier, under `task.all`, on 16 workers: the line twice in 2 of 60 runs. `test_what_they_report` checks t29's stderr on 4 workers, so it can fail by chance; t34 is left out of `EXPECTED_STDERR` for this reason (its stdout and status are checked on every run). A fix: claim the report with an exchange on a flag before writing, and let the others park.
- Inside `lib/std/task.my`, `cancel(a)` still isn't taken as `task.cancel` (`'a' is the result of a child task`), as the first attempt found; `first` and the tests use `__cancel_after(a, 0)` and `__disarm`, as `timeout` does.
- `#test` functions of a `lib/std` module cost every program that imports it check time (about 6 ms here, from 18 test functions).
