---
id: MYLA-611
title: "A wide tree of tasks on one worker once peaked at 234 MB instead of 64 MB"
type: bug
status: todo
priority: low
labels: [runtime, concurrency, tests, round-6]
---
Found by the integration of round 6's wave 3: one run of the full suite (`MYLA_REQUIRE_TARGETS=1 scripts/test.sh`, the tip of `round6-wave3`, 2026-11-13) failed `tests.burn.test_scheduling.Scheduling.test_a_wide_tree_of_tasks_needs_memory_for_its_depth`:

```
AssertionError: 703.06640625 not less than 692.375 : lifo 234 MB, fifo 692 MB
```

The test builds `_WIDE` (300,000 tasks through `task.all`) and runs it natively with `MYLA_THREADS=1`, depth first (the default, D110) and with `MYLA_SCHED=fifo`, and compares the peak resident memory (`ru_maxrss`). Alone it gives 64 MB depth first against 692 MB breadth first, every time: three runs alone and three beside five busy loops, all 64 against 692. Only that once, inside the full suite (whose suites run in parallel), was the depth-first peak 234 MB, while the breadth-first one stayed at 692 MB to the megabyte.

On one worker the order the tasks run in should not depend on the machine's load, so a peak 3.7 times higher means something on that run was not the plain depth-first walk: a timer, the stuck check, a helper thread's look at the queues, or memory the kernel accounted differently (transparent huge pages under memory pressure?). Wave 3 changed no runtime code (labels, comments, docs), so it is older than the wave.

- [ ] Reproduce: run the test in a loop under the full suite's load, or with memory pressure (`stress-ng --vm`), and record the peaks
- [ ] Find what makes a one-worker run hold more frames than the depth-first walk does (or find that it is the kernel's accounting)
- [ ] Fix it, or make the test measure what it means to (the frames held, rather than the peak resident memory) if the extra is the kernel's
