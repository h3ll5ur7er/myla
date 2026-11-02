---
id: MYLA-197
title: t08_failing_child_cancels_its_children depends on timing
type: bug
status: done
priority: medium
labels: [concurrency, tests, flaky]
---
Found while re-running the suites for the October 2026 review ([[Project/Review-2026-10]]). `tests/burn/concurrency_stress/t08_failing_child_cancels_its_children.my` expects `('', 1)`: the entry's 2,000 awaited calls of the actor are meant to be cut short by a child that panics after 20. Under CPU load the entry wins the race and prints `main still runs` first: in the Python interpreter 8 of 30 runs at the unchanged `f46c8b8` with six busy processes beside it, and once natively with 16 workers during a full burn run. D97 says which of two events at about the same time comes first depends on timing; the program's expectation doesn't.

- [x] Make the outcome independent of timing: the entry waits for something the failing child does before its loop (an actor flag set by `fail_soon` before the panic), or the test accepts both outputs and checks only the exit status and that the failure is reported
- [x] The same look at the other `t08_` programs and at `test_tasks_on_any_number_of_workers`

## Evidence

- The entry now calls the actor for ever: only the child's failure ends the program, so no ordering is left to chance; the other `t08_` programs either await the failing child or print nothing, and the stress suite's other programs and `test_tasks_on_any_number_of_workers` compare outputs that don't depend on timing.
- On every implementation and on 1 and 4 workers (3 runs each): `('', 1)` with `runtime error: failure in a child`.
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
