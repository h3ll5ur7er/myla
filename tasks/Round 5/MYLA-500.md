---
id: MYLA-500
title: "test_time's async-read test races its feeder under load"
type: bug
status: review
priority: low
labels: [tests, concurrency, round-5]
---
Found by [[MYLA-430]], and named as a passing failure in [[MYLA-390]], [[MYLA-389]], [[MYLA-392]] and [[MYLA-396]] before. `tests.burn.test_time.Time.test_an_async_read_lets_the_other_tasks_run` (interpreter runner) feeds its program three lines 0.15 s apart and asserts that the first line of output is a tick (`t`), so that the worker wasn't blocked by the read. On a loaded machine (four lanes on four cores, load average 6) the first output is `line 0` about one run in three, at the base `bb5380d` as with MYLA-430's change, so the test fails alone too, not only in a parallel suite:

```
python3 -m unittest tests.burn.test_time.Time.test_an_async_read_lets_the_other_tasks_run
AssertionError: 'line 0' != 't'
```

The program's own start (loading and checking its imports) can take longer than the feeder's first 0.15 s, and then a line is waiting before the first tick is due. The test should wait for the program to start (the feeder could wait for the first tick on the program's stdout before it writes), not assume 0.15 s is enough.

- [x] The feeder writes its first line only after the program's first tick (or the assertion allows a line before the first tick when the read was ready at once)

## Evidence

The test now feeds its program itself (`fed_after_a_tick` in [[tests/burn/test_time.py]]): the program's stdin and stdout are pipes, a thread writes the three lines 150 ms apart, and the first one only once the program has printed a tick. The reader task starts before the ticker, so by the first tick its `read_line_async` is pending, and the tick shows that the worker went on while it waited. What the test checks is unchanged or stricter: a tick within 30 s while no input had come (else the feeder gives up, closes stdin and the test fails with `no tick while the read was pending: …`), the first output line a tick, the three lines in order, `3 lines, 10 ticks`. `FEEDER` stays for `test_two_readers_of_one_descriptor`.

- **It still catches a blocked worker.** With the program's `await r.read_line_async()` replaced by the blocking `r.read_line()`, both runners fail: `AssertionError: False is not true : no tick while the read was pending: ['t', 't', …, '0 lines, 10 ticks']` (the ticks only came after the feeder gave up).
- **30 runs under load, before and after.** `python3 -m unittest tests.burn.test_time.Time.test_an_async_read_lets_the_other_tasks_run`, 30 times in a row beside busy loops (the machine is shared with five other lanes):

  | Busy loops | Load at the end | Before | After |
  | --- | --- | --- | --- |
  | 5 | 6.1 | 1 of 30 failed | |
  | 8 | 8.3 | 1 of 30 failed | 0 of 30 failed |
  | 12 | 16 to 18 | 2 of 30 failed | 0 of 30 failed |

  Each failure was `AssertionError: 'line 0' != 't'`. Alone, at load 1, the test takes 1.0 s.
