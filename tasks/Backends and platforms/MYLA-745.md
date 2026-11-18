---
id: MYLA-745
title: "Timing tests that fail under a full run's load"
type: bug
status: review
priority: low
labels: [testing]
---
Tests that pass alone and fail now and then when the whole suite, or `scripts/test-target.py`'s suites in parallel, load the machine. The owner put them off (2026-11-15: "we will deal with the flaky tests later").

- `test_stdio`'s CPU-ratio case.
- `test_process`'s `test_children_run_in_parallel`.
- `test_reactor_scaling.RoundTrips.test_round_trips_beside_many_waiting_frames` on aarch64 under qemu (CI's `targets` job on PR #78, 2026-11-16): `45470 µs beside 50,000 waiting frames, 25423 µs alone` against its limit of 1.5 × alone + 5,000 µs; MYLA-547 saw it under load too, and it passes alone there.
- `test_http.TimeLimits.test_idle_non_reading_and_slow_handled_connections`: `wait_for_sockets(self.server_pid, 1, 10)` gave 2 for both the interpreted and the built server in `scripts/test.sh` and in `scripts/test-target.py x86_64-windows` on `d1d8db9` (2026-11-16), and passed alone twice each way. MYLA-555 saw the same once in 9 runs under load. Since [[MYLA-706]] it runs for Windows too.

- [x] Each made robust (its limits a comparison with an unloaded measurement, D197, or the condition waited for instead of a time), or excused under load with the reason

## Evidence

Each now compares with a twin measured beside it, on the machine as loaded then, or waits for its condition; none is skipped.

- `test_stdio.NonBlockingOutput` (the CPU ratio): its twin, the same program read as fast as it writes, gives the CPU its start and its writes take; the slowly read run may use at most a quarter of the time it waited (`wall - wall0`) more than that. Before, a fixed share of the wall time (0.4, 0.6 under an emulator).
- `test_selfhost_codegen.test_children_run_in_parallel`: the program on one worker, run in turn with it on every worker, the best of three each, each less its time with no work (an argument: its start, most of a run under Wine, where the first version saw 1.37 s on one worker and 1.06 s on every one); on every worker the work must take less than two thirds of one worker's. And a count, whatever the load: once the work is done (the program then waits for a line), at least two of the process's threads each took a tenth of its CPU time (natively on one worker `[125]`, 1 thread; on every worker `[30, 30, 29, 29]`, 4). Under qemu-aarch64 only the count: there its threads gave the 8 children 1.3 CPUs (3.2 s on 8 workers, 3.6 s on one, 2026-11-18 under the other lanes' load), which `test-target.py aarch64-linux` failed on with the twin (4.75 s against 5.15 s), and so would the CPU ratio before. Before, a CPU time of 1.5 times the wall time, which the other processes of a full run took away.
- `test_reactor_scaling.RoundTrips.test_round_trips_beside_many_waiting_frames`: alone measured before the 50,000 waiting frames and again after they are cancelled, the slower of the two the baseline (the echo serves 15,000 round trips for it).
- `test_http.TimeLimits.test_idle_non_reading_and_slow_handled_connections`: the condition (the server down to its listener) waited for at most 30 s, not 10, and a failure lists the server's sockets with their ports, states and queues (`socket_states`). Not reproduced here at BASE: 6 of 6 alone, 8 of 8 beside 8 CPU-bound processes.
- `test_http.TimeLimits.test_kept_connections_wait_parked`, seen here under load (the interpreted server: a kept connection's next request found it closed, `b''`): the 200 first requests were sent one after the other while the first connections' `idle_ms` (1.5 s) ran; they are sent at once now and `idle_ms` is 3 s (closed within 4.5 s, not 3).
- The Windows `t15` stress case: [[MYLA-781]].

Each passes alone and beside the others' load here (2026-11-18): the suites `test_stdio`, `test_reactor_scaling`, `test_http`, and `test_selfhost_codegen`'s case.

**Suites** (2026-11-18, this branch): `scripts/test.sh` 1,859 tests OK; `scripts/test-target.py` x86_64-windows 39 of 39 suites, aarch64-linux 38 of 39 then 39 (test_children_run_in_parallel, [[MYLA-745]]), wasm32-wasi 39 of 39; `tests.burn.test_windows` and `test_windows_runner` 73 tests OK under Wine; `scripts/windows-runner.py run --wine --runs 3`: 153 passed, 0 failed, 17 skipped of 170 cases (round 7's integration: 152 of 170, t15 failing); the bootstrap's fixed point, `scripts/check-seed.sh` and its Windows run.
