---
id: MYLA-611
title: "A wide tree of tasks on one worker once peaked at 234 MB instead of 64 MB"
type: bug
status: review
priority: low
labels: [runtime, concurrency, tests, round-6]
---
Found by the integration of round 6's wave 3: one run of the full suite (`MYLA_REQUIRE_TARGETS=1 scripts/test.sh`, the tip of `round6-wave3`, 2026-11-13) failed `tests.burn.test_scheduling.Scheduling.test_a_wide_tree_of_tasks_needs_memory_for_its_depth`:

```
AssertionError: 703.06640625 not less than 692.375 : lifo 234 MB, fifo 692 MB
```

The test builds `_WIDE` (300,000 tasks through `task.all`) and runs it natively with `MYLA_THREADS=1`, depth first (the default, D110) and with `MYLA_SCHED=fifo`, and compares the peak resident memory (`ru_maxrss`). Alone it gives 64 MB depth first against 692 MB breadth first, every time: three runs alone and three beside five busy loops, all 64 against 692. Only that once, inside the full suite (whose suites run in parallel), was the depth-first peak 234 MB, while the breadth-first one stayed at 692 MB to the megabyte.

On one worker the order the tasks run in should not depend on the machine's load, so a peak 3.7 times higher means something on that run was not the plain depth-first walk: a timer, the stuck check, a helper thread's look at the queues, or memory the kernel accounted differently (transparent huge pages under memory pressure?). Wave 3 changed no runtime code (labels, comments, docs), so it is older than the wave.

- [x] Reproduce: run the test in a loop under the full suite's load, or with memory pressure (`stress-ng --vm`), and record the peaks — reproduced every time by the test's process holding memory, not by load: see below
- [x] Find what makes a one-worker run hold more frames than the depth-first walk does (or find that it is the kernel's accounting) — the kernel's accounting: `ru_maxrss` counts the test process's image that `fork` copied
- [x] Fix it, or make the test measure what it means to (the frames held, rather than the peak resident memory) if the extra is the kernel's — the program reports its own peak (`VmHWM`)

## The cause

Not the runtime: the measure. The test forks the Python process that runs it and execs the program, and reads the child's `ru_maxrss` from `wait4`. On Linux a process's `ru_maxrss` is the largest of its images' high-water marks, and `exec` records the old image's (`exec_mmap` → `setmax_mm_hiwater_rss`): the image `fork` copied from the test's process, whose private pages the child counts as its own. `scripts/test.sh` runs the whole burn suite in one Python process (`unittest discover`), which had grown to about 234 MB by the time it reached `test_scheduling`; alone it is about 20 MB, under the program's 64. So the depth-first peak read the test runner's size, and the breadth-first one (692 MB, more than the runner) its own. Transparent huge pages play no part: a program `myla build` builds asks for none, and the kernel here gives them only on `madvise` ([[MYLA-608]] changes that for the toolchain alone).

## What changed

`tests/burn/test_scheduling.py`: `_WIDE` prints its own peak resident memory at its end (`VmHWM` of `/proc/self/status`, the high-water mark of the program's image only), and the test compares those instead of `ru_maxrss`. The bound (depth first at least three times less than breadth first) is unchanged.

## Evidence

A driver (scratch, not committed) runs the test from a Python process that first touches a ballast of N MB, as the suite's process had grown:

| ballast | before (`ru_maxrss`) | after (`VmHWM`) |
| --- | --- | --- |
| 0 MB | OK (64 against 692 MB) | OK |
| 230 MB | FAIL: `lifo 247 MB, fifo 692 MB` | OK |
| 600 MB | FAIL: `lifo 617 MB, fifo 692 MB` | OK |

The program alone, after: `MYLA_THREADS=1` 65,128 kB depth first, 709,128 kB with `MYLA_SCHED=fifo` (the same as `ru_maxrss` read from a small parent). `python3 -m unittest tests.burn.test_scheduling`: 3 tests OK.
