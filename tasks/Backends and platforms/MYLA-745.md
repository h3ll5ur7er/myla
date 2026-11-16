---
id: MYLA-745
title: "Timing tests that fail under a full run's load"
type: bug
status: backlog
priority: low
labels: [testing]
---
Tests that pass alone and fail now and then when the whole suite, or `scripts/test-target.py`'s suites in parallel, load the machine. The owner put them off (2026-11-15: "we will deal with the flaky tests later").

- `test_stdio`'s CPU-ratio case.
- `test_process`'s `test_children_run_in_parallel`.
- `test_reactor_scaling.RoundTrips.test_round_trips_beside_many_waiting_frames` on aarch64 under qemu (CI's `targets` job on PR #78, 2026-11-16): `45470 µs beside 50,000 waiting frames, 25423 µs alone` against its limit of 1.5 × alone + 5,000 µs; MYLA-547 saw it under load too, and it passes alone there.
- `test_http.TimeLimits.test_idle_non_reading_and_slow_handled_connections`: `wait_for_sockets(self.server_pid, 1, 10)` gave 2 for both the interpreted and the built server in `scripts/test.sh` and in `scripts/test-target.py x86_64-windows` on `d1d8db9` (2026-11-16), and passed alone twice each way. MYLA-555 saw the same once in 9 runs under load. Since [[MYLA-706]] it runs for Windows too.

- [ ] Each made robust (its limits a comparison with an unloaded measurement, D197, or the condition waited for instead of a time), or excused under load with the reason
