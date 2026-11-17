---
id: MYLA-755
title: "A busy worker glances at the poller every 64 frames, not by time: under load no worker polls for seconds"
type: bug
status: review
priority: medium
labels: [concurrency, performance]
---
Found by [[MYLA-753]]. std.rt's poller is waited in by an idle worker, and a busy one glances at it every 64 frames it runs (`exec_run`'s `turns & 63`, [[lib/std/rt.my]], D124). When every worker stays busy and frames are slow (a loaded machine, [[MYLA-754]]'s convoy), the glances come seconds apart, and so does every wake-up for I/O: in a traced run of `SOCKETS 200 50` on 16 workers under Wine (the machine's load average about 60, [[MYLA-753]]'s fix in), no worker took a packet from 6143846 ms to 6147222 ms, while the workers armed about 100 handles, and the server's parked connection, whose request had come at once, was dropped at its 5 s.

- [x] A busy worker glances once a time has passed since the last poll of any worker (a millisecond, read from the clock every so many turns, or the timers' clock), as Go's `sysmon` and tokio's event interval bound a ready descriptor's wait whatever the run queues hold
- [x] A test that holds every worker busy and measures how long a ready socket waits

## Not done in [[MYLA-753]]'s round (2026-11-16)

Not small: in the traced run each of the 16 workers ran about six frames in those 3.4 s, so a glance every so many turns, however few, wouldn't have come; bounding the wait by time needs the clock read at every turn (a `clock_gettime` system call in this runtime on Linux, which has no vDSO path), a cost on every task switch, or a time another thread keeps (a runtime variable, so a seed staged, D207). With [[MYLA-754]] and [[MYLA-756]] fixed the loaded runs above hung none, so this waits.


## What changed (2026-11-16, Windows wave 6's Signals lane)

`exec_run` ([[lib/std/rt.my]]) keeps four words of its own while descriptors are watched: the turns since it read the clock, how many turns go between reads, when it read it and when this worker last glanced. It reads `os.clock_ns()` every `every` turns and glances (`exec_glance`, as before) once `GLANCE_NS` (1 ms) has passed since its last glance; the first turn with descriptors watched counts as a glance, so the frames queued then run first as they did (`test_net`'s held read relies on that order). `glance_every` sets the reads' spacing: as many turns as took about `GLANCE_READ_NS` (250 µs), from 1 to `GLANCE_TURNS` (64), at most twice as many as before, so short turns read the clock every 64 (on Linux a system call, as the glance every 64 turns was: a cost about BASE's), and long ones at each turn, from the read that sees them long. Nothing new is shared: no runtime variable, so no seed is staged (D207). The idle worker's spin and poll are unchanged.

What it doesn't bound: a run of 64 turns that are short and then become long at once costs at most those 64 long turns before the next read (the read after them sets `every` to 1); a single frame that computes without suspending holds its worker, as before.

## Proposals (accepted 2026-11-17: D245)

1. **A clock read about every 250 µs of turns, at most every 64, each worker its own** (built): the glance once a millisecond has passed since this worker's last. Alternatives:
   - **The clock at every turn**: the bound needs no adaptation, but on Linux each read is a `clock_gettime` system call (130 ms for a million reads here, `std.time.now_ns()`, 2026-11-16, 0adad44, about 3.5 turns of the executor's): 8 tasks yielding 200,000 times each beside a watched descriptor took 276 ms against 61 ms (median of 9, 1 worker), where this one takes 62.
   - **A shared time of the last poll** (a runtime variable, `__exec_polled`, D207 staged on all three seeds as every target's compiler emits it): a busy worker would glance only when no worker polled for a millisecond, so 16 busy workers glance once a millisecond, not up to 16 times; the clock is read as often as here. Each worker's glance costs a failed exchange of `__exec_polling` when another polls, and a wait of no time when not; not worth a seed now.
   - **A cheap counter** (a primitive for `rdtsc` and `cntvct_el0`, calibrated against the clock): a read at every turn for a few cycles, but a new primitive on three back ends and the interpreter, staged, and the TSC's trust across cores and VMs.
   - **A monitor thread** (Go's sysmon): a thread of the runtime's on each target that wakes while descriptors are watched and every worker is busy; bounds the wait whatever a frame does, but wakes the process itself, which [[MYLA-744]] just removed on Windows.
   - **A smaller count** (every 8 turns): still unbounded in time, as the traced run (six frames a worker in 3.4 s) shows.

Suggested decision row: "**A busy worker glances at the poller once a millisecond has passed since its last glance** ([[MYLA-755]], D124): `exec_run` reads the monotonic clock every so many turns (`glance_every`: about every 250 µs of turns, at most every 64) and glances once 1 ms passed; each worker keeps its own times, no runtime variable | The owner's acceptance of the recommendation (2026-11-16). A glance every 64 turns came seconds apart when every worker ran slow frames; the clock at every turn costs a system call a turn on Linux (8 tasks yielding beside a watched descriptor: 276 ms against 62 ms); a shared time would need a seed staged for the same reads of the clock"

## Evidence

- **Test first**: `test_reactor_scaling.BusyWorkers` (as many tasks as workers running frames of 20 ms, a yield after each, the first writing a byte after its 10th frame to a socket a task awaits in `read_async`; the ms from the write to the reader's wake-up, below 200 on 1 and 2 workers) at BASE `478d656`'s library: `FAIL` 1,060 ms on 1 worker, 1,040 ms on 2 (the glance at the 64th frame); after: `PASS`.
- **The cost** (2026-11-16, 7af6e7f's library against BASE's, the same compiler, this 4-CPU machine, load average about 1; `yields.my`: 8 tasks each awaiting `task.yield()` 200,000 times, plain and beside a task in `accept_async`, the median of 9 runs interleaved): 1 worker plain 58 ms both; with the descriptor watched BASE 61 ms, this branch 62 ms (the clock at every turn: 276 ms); 4 workers plain 318 against 312 ms, watched 375 against 370 ms (the queues' contention dominates; best of 9: 320 against 255 ms). A second run under the other lanes' load (load average 7.5, median of 11): watched 64 against 64 ms on 1 worker, 96 against 82 on 4; the clock at every turn 289 and 314. A program without descriptors watched pays what it did (one load a turn).
- **Suites** (2026-11-16, this branch): `scripts/test-target.py x86_64-windows test_reactor_scaling test_net test_http test_process` 4 of 4; the same on `aarch64-linux` 4 of 4; `wasm32-wasi test_reactor_scaling test_net` 2 of 2 (`BusyWorkers` skipped there: WASI has no sockets); `python3 -m unittest tests.burn.test_reactor_scaling` natively 7 OK, `tests.burn.test_net` 21 OK (the held read's warning failed natively and under Wine with an immediate first glance, which ran the connecting task first: fixed by counting the first turn as a glance); `lib/std/rt.my`'s 41 cases interpreted (`glance_every`'s 6 among them); `test_windows` and `test_windows_runner` 50 OK (1 skipped); `scripts/windows-runner.py build` 108 programs, 160 cases, and `run --wine --runs 3` 148 passed, 0 failed, 12 skipped (the console cases, as before); `scripts/test.sh fast` 1,005 tests OK (7 skipped); `scripts/check-seed.sh`: each seed bootstraps the sources, none changed; the workflow parses (PyYAML); the bootstrap's fixed point holds (29,277,478 bytes).
- **The other targets' assembly**: BASE's `stage3` and this branch's, both given this branch's library, give byte-identical assembly for `selfhost/gen_main.my`, `examples/maps.my` and `examples/concurrency.my` on `x86_64-linux`, `aarch64-linux` and `wasm32-wasi`; on `x86_64-windows` they differ in `__win_on_ctrl`'s eight lines and the import list's `PostQueuedCompletionStatus` ([[MYLA-744]]). The library's change gives every native program's `exec_run` its new lines and `glance_every`, on every target, by design.
