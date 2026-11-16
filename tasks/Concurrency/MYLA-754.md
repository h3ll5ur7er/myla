---
id: MYLA-754
title: "std.rt's spin locks never give their CPU up: more workers than CPUs convoy behind a preempted holder"
type: bug
status: todo
priority: high
labels: [concurrency, performance, windows]
---
Found by [[MYLA-753]]. std.rt's `take_lock` ([[lib/std/rt.my]]: the queues', the actors' and the timers' locks) spins on `__pause()` until the lock is free. With more workers than CPUs (`MYLA_THREADS=16` on CI's 4-CPU machines), a worker preempted while it holds the timers' lock leaves the others spinning through their whole time slice. Windows' scheduler gives long slices (a server's especially), so there it costs most:

- CI's `windows` job (master's run 43825708390, 2026-11-16): `net/sockets-and-children` took 8.0 s for its three steps, nearly all of it the 16-worker one; the 1- and 4-worker steps together under a second (the failing run's 300.5 s for the case was step 3's 300 s alone).
- Under Wine on this 4-CPU machine, `SOCKETS 200 50` (tests/burn/test_windows.py) on 16 workers: 3.8 to 4.8 s, 11 to 15 s of user CPU; with `take_lock` giving the CPU up after 64 spins (`Sleep(0)`, a test-only copy of the library), 1.0 to 1.1 s and 0.6 s of user CPU (three runs each, 2026-11-16, `983fcc3`). A sampled profile of the unchanged program (gdb, 40 samples of every thread's program counter) had its threads in `wait_fds`, `watches_closed`, `task_end` and `timers_fire` (each spinning in its inlined `take_lock`) far more than anywhere else of the program's.

So the busy phase of a program with tasks grows with the workers past the CPUs, and with it every wait for I/O ([[MYLA-753]]'s requests past the HTTP server's 5 s).

- [ ] `take_lock` gives its CPU up after a bounded spin (as std.platform's `net_lock` does on Windows: 64 pauses, then `SwitchToThread`), or parks on the lock's word (`os.park`, a waiter's count, `unpark_one` on release) where it is held longer
- [ ] Linux, aarch64 and wasm32 keep their assembly unless the change is for them too (a `os.TARGET == "x86_64-windows"` test folds, as `program_paths`' does), or measured on them as well
- [ ] `SOCKETS` on 16 workers measured under Wine and on CI's runner before and after
