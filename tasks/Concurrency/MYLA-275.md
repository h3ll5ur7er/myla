---
id: MYLA-275
title: "A busy machine could end a program with \"every task waits for another one\" (the executor's stuck check)"
type: bug
status: review
priority: high
labels: [concurrency, runtime, aarch64]
---
Found by the cold verification of [[Project/Reflection-2026-11]]'s commit (2026-11-04). `tests.burn.test_aarch64.Aarch64Time.test_a_child_process_waited_for_without_blocking_the_worker`, on 4 workers under `qemu-aarch64`, failed once in six runs: the program printed its ticks and `4 6 3` and `5`, then `runtime error: every task waits for another one` with exit 1. Expected: the remaining lines (`200000 200000`, `not found`, `timed out`, `true`, `5`) and exit 0. The same commit's compiler is byte for byte `master`'s (the seed check passes), so the failure is `master`'s too. The next five runs passed.

A likely cause, to confirm: `exec_idle` in [[lib/std/rt.my]] decides that no task can go on by reading `__exec_idle`, `__timer_count`, `__watch_count`, `__exec_waking` and the queues with plain loads, in an order its comment relies on ("the counts first, then the wake-ups in flight, then the queues again"). x86-64 doesn't reorder loads with loads, so the order holds there. aarch64 may reorder them. An idle worker could then see `__watch_count` already 0 after another worker took a child's frame off the watches, but `__exec_waking` still at its old 0, and stop the program while that frame is about to be queued. qemu-user on x86-64 rarely shows such reorderings. This is the kind of fault [[MYLA-267]] is about.

- [x] Reproduce: run the test's program (`PROCESS` in [[tests/burn/test_time.py]]) many times on 4 workers under qemu
- [x] Fix the stuck check; the ordering of its reads made explicit
- [x] A test that catches it, run many times without a failure

## The cause (2026-11-04)

Not the memory order, as first suspected: the check was racy on every processor. Alone, the program never failed (0 of 60 under qemu, 0 of 40 natively). Eight copies at once on the four-core machine failed under qemu 13 times in 320 runs, natively 0 in 400. Every failure was the stuck error.

The error path, instrumented to print the counts it had just decided on, showed states that weren't stuck: `idle=3`, `watches=2`, `waking=1 polling=1`. The check read `__exec_idle` first and the queues last:

1. Worker C, going idle, reads `__exec_idle` = 4, all four workers idle.
2. Worker D, idle and having seen a queued frame, leaves `exec_idle` (3) and takes the frame (`exec_find`).
3. C reads the timers, the watches and `__exec_waking` (all 0), then the queues: empty, as D took the frame.
4. C ends the program while D runs the frame, which watches its child's pipes next.

On x86-64 the window is a few instructions; under qemu, with threads descheduled on a busy machine, it is wide.

## The fix

[[lib/std/rt.my]]:
- `exec_idle` bumps a generation, `__exec_gen` (a new runtime variable, [[selfhost/codegen.my]]), when a worker leaves, before it can take a frame.
- `exec_all_waiting` decides only if the generation didn't change during the check: every worker was idle throughout. While every worker is idle, a frame only moves from the timers or the watches to a queue, counted in `__exec_waking` all the way, which the read order (timers, watches, waking, queues) can't miss.
- The check's reads are read-modify-writes (`__fetch_add64(p, 0)`), ordered on every processor; the check is rare, so they cost nothing measurable.

Also [[selfhost/ir_a64.my]]: `__cas64` gets the `dmb ish` its success path lacked, as the exchanges have (publish, then look; [[MYLA-267]]).

## Evidence

- The contention harness (8 copies at once, 40 runs each, 4 workers, under qemu): 13 failures in 320 runs before, 0 in 320 after.
- `test_child_processes_waited_for_by_programs_running_at_once` in [[tests/burn/test_time.py]] (natively and, through `Aarch64Time`, under qemu): 64 runs, 8 at a time. With 32 runs it failed 2 of 7 times on the old code; with 64 it passes 5 of 5 times on the new code, on both targets, in about 7 s.
- The bootstrap reaches its fixed point; the seed is updated.

What this didn't change: unlocking is still a plain store (`__store64(lock, 0)`), which on aarch64 hardware lets a critical section's stores appear after the unlock. qemu on x86-64 can't show that; it stays with [[MYLA-267]].
