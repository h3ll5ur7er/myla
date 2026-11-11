---
id: MYLA-500
title: "test_time's async-read test races its feeder under load"
type: bug
status: todo
priority: low
labels: [tests, concurrency, round-5]
---
Found by [[MYLA-430]], and named as a passing failure in [[MYLA-390]], [[MYLA-389]], [[MYLA-392]] and [[MYLA-396]] before. `tests.burn.test_time.Time.test_an_async_read_lets_the_other_tasks_run` (interpreter runner) feeds its program three lines 0.15 s apart and asserts that the first line of output is a tick (`t`), so that the worker wasn't blocked by the read. On a loaded machine (four lanes on four cores, load average 6) the first output is `line 0` about one run in three, at the base `bb5380d` as with MYLA-430's change, so the test fails alone too, not only in a parallel suite:

```
python3 -m unittest tests.burn.test_time.Time.test_an_async_read_lets_the_other_tasks_run
AssertionError: 'line 0' != 't'
```

The program's own start (loading and checking its imports) can take longer than the feeder's first 0.15 s, and then a line is waiting before the first tick is due. The test should wait for the program to start (the feeder could wait for the first tick on the program's stdout before it writes), not assume 0.15 s is enough.

- [ ] The feeder writes its first line only after the program's first tick (or the assertion allows a line before the first tick when the read was ready at once)
