---
id: MYLA-197
title: t08_failing_child_cancels_its_children depends on timing
type: bug
status: todo
priority: medium
labels: [concurrency, tests, flaky]
---
Found while re-running the suites for the October 2026 review ([[Project/Review-2026-10]]). `tests/burn/concurrency_stress/t08_failing_child_cancels_its_children.my` expects `('', 1)`: the entry's 2,000 awaited calls of the actor are meant to be cut short by a child that panics after 20. Under CPU load the entry wins the race and prints `main still runs` first: in the Python interpreter 8 of 30 runs at the unchanged `f46c8b8` with six busy processes beside it, and once natively with 16 workers during a full burn run. D97 says which of two events at about the same time comes first depends on timing; the program's expectation doesn't.

- [ ] Make the outcome independent of timing: the entry waits for something the failing child does before its loop (an actor flag set by `fail_soon` before the panic), or the test accepts both outputs and checks only the exit status and that the failure is reported
- [ ] The same look at the other `t08_` programs and at `test_tasks_on_any_number_of_workers`
