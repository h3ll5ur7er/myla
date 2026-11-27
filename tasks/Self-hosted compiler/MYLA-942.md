---
id: MYLA-942
title: "The interpreter ignores MYLA_SCHED and MYLA_TIME on Windows: it read them from /proc/self/environ"
type: bug
status: done
priority: high
labels: [interpreter, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group E), in the native Windows run 277: `test_scheduling.test_one_worker_runs_tasks_in_the_interpreters_order` got the default (newest first) order from `myla run` under every `MYLA_SCHED` (`fifo`, `seed:1`, …), so the five orders were one (`1 != 5`), while the built program took each; `test_time`'s `test_many_sleepers_beside_a_busy_task` (`false` for `true`) and `test_the_virtual_clock_takes_no_time` (10 s, not under 5) ran `MYLA_TIME=virtual` on the real clock.

`selfhost/interp.my`'s `sched_from_env` and `time_from_env` read the variables from `/proc/self/environ`, which Windows doesn't have (Wine maps it to Linux's, so the Wine runs passed). They now ask std.process's `env`, which every target has (its `__getenv`; on Windows a name in either case, [[MYLA-798]]); `sched_in` and `env_entry`, which parsed that file's text, went.

- [x] `sched_from_env` and `time_from_env` through `std.process.env`
- [x] Evidence: under Wine the Windows-built interpreter (`interp_main.my --target x86_64-windows`) runs `tests/burn/data/sched_order.my` with `MYLA_THREADS=1` as `f4 f3 f3.` by default, `f0 f1 f1.` with `MYLA_SCHED=fifo` and `f4 f2 f1` with `seed:1`, the orders the built program takes; on Linux test_scheduling and test_time pass as before and the bootstrap reaches its fixed point. On Windows itself: the next `burn-windows` run
