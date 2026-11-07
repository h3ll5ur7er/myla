---
id: MYLA-302
title: The burn suite's timing and memory bounds on a busy runner
type: chore
status: review
priority: low
labels: [tests]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]], R27): `test_children_run_in_parallel` asserted `cpu > 1.5 × wall` once and failed in a loaded full run (1.28 s against 0.91 s), and the suite has more timing and memory bounds that a busy runner could turn red.

- [x] The parallelism test robust to load
- [x] Every other bound looked at: how far it is from what it guards against

## Evidence

- `test_children_run_in_parallel` takes the best of three runs (patched on master with the review) and skips on one CPU.
- The other bounds, each against the failure it guards: `test_time`'s `took < 5.0` (four), against a sleep of 10 s the program must not wait out; its programs' `now_ms() - start < 4000` against a sleep of 5 s (`CANCEL`, `TIMEOUT`), `< 3000` around a 50 ms timeout (the reactor program), `< 1500` around a 50 ms timeout (`READ_TIMEOUT`, against a read that would block): 30 to 60 times the time the work takes, ample under qemu too. The peak-memory bounds (`test_selfhost_codegen`: 30 MB and 64 MB) measure memory, which load doesn't change; natively the deep-task program peaks at 18 MB against its 64. None needed a change.
