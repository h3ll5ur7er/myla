---
id: MYLA-275
title: "aarch64: a program waiting on a child process sometimes ends with \"every task waits for another one\" on 4 workers"
type: bug
status: backlog
priority: high
labels: [concurrency, runtime, aarch64, memory-ordering]
---
Found by the cold verification of [[Project/Reflection-2026-11]]'s commit (2026-11-04). `tests.burn.test_aarch64.Aarch64Time.test_a_child_process_waited_for_without_blocking_the_worker`, on 4 workers under `qemu-aarch64`, failed once in six runs: the program printed its ticks and `4 6 3` and `5`, then `runtime error: every task waits for another one` with exit 1. Expected: the remaining lines (`200000 200000`, `not found`, `timed out`, `true`, `5`) and exit 0. The same commit's compiler is byte for byte `master`'s (the seed check passes), so the failure is `master`'s too. The next five runs passed.

A likely cause, to confirm: `exec_idle` in [[lib/std/rt.my]] decides that no task can go on by reading `__exec_idle`, `__timer_count`, `__watch_count`, `__exec_waking` and the queues with plain loads, in an order its comment relies on ("the counts first, then the wake-ups in flight, then the queues again"). x86-64 doesn't reorder loads with loads, so the order holds there. aarch64 may reorder them. An idle worker could then see `__watch_count` already 0 after another worker took a child's frame off the watches, but `__exec_waking` still at its old 0, and stop the program while that frame is about to be queued. qemu-user on x86-64 rarely shows such reorderings. This is the kind of fault [[MYLA-267]] is about.

- [ ] Reproduce: run the test's program (`PROCESS` in [[tests/burn/test_time.py]]) many times on 4 workers under qemu, and on arm64 hardware if available
- [ ] Order the stuck check's loads (acquire loads, or a barrier between them, through [[MYLA-264]]'s typed atomics), and the matching stores as release; check `timer_add`, `watch_take` and the wake-ups against it
- [ ] The test run many times on 4 and 16 workers without a failure
