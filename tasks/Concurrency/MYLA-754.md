---
id: MYLA-754
title: "std.rt's spin locks never give their CPU up: more workers than CPUs convoy behind a preempted holder"
type: bug
status: review
priority: high
labels: [concurrency, performance, windows]
---
Found by [[MYLA-753]]. std.rt's `take_lock` ([[lib/std/rt.my]]: the queues', the actors' and the timers' locks) spins on `__pause()` until the lock is free. With more workers than CPUs (`MYLA_THREADS=16` on CI's 4-CPU machines), a worker preempted while it holds the timers' lock leaves the others spinning through their whole time slice. Windows' scheduler gives long slices (a server's especially), so there it costs most:

- CI's `windows` job (master's run 43825708390, 2026-11-16): `net/sockets-and-children` took 8.0 s for its three steps, nearly all of it the 16-worker one; the 1- and 4-worker steps together under a second (the failing run's 300.5 s for the case was step 3's 300 s alone).
- Under Wine on this 4-CPU machine, `SOCKETS 200 50` (tests/burn/test_windows.py) on 16 workers: 3.8 to 4.8 s, 11 to 15 s of user CPU; with `take_lock` giving the CPU up after 64 spins (`Sleep(0)`, a test-only copy of the library), 1.0 to 1.1 s and 0.6 s of user CPU (three runs each, 2026-11-16, `983fcc3`). A sampled profile of the unchanged program (gdb, 40 samples of every thread's program counter) had its threads in `wait_fds`, `watches_closed`, `task_end` and `timers_fire` (each spinning in its inlined `take_lock`) far more than anywhere else of the program's.

So the busy phase of a program with tasks grows with the workers past the CPUs, and with it every wait for I/O ([[MYLA-753]]'s requests past the HTTP server's 5 s).

- [x] `take_lock` gives its CPU up after a bounded spin (as std.platform's `net_lock` does on Windows: 64 pauses, then the platform's `yield_cpu`)
- [x] On every target, measured on Linux too (the change is for them as well: a lock holder can be preempted there by spinners just the same)
- [ ] `SOCKETS` on 16 workers measured on CI's runner before and after (the next run of the `windows` job)

## What changed

- **`take_lock`** ([[lib/std/rt.my]]): after 64 spins of `__pause()`, `os.yield_cpu()`, then 64 more. A lock taken at once costs what it did (one exchange).
- **`yield_cpu`**, a function of each platform module (no primitive: what the seed knows, so nothing is staged): `sched_yield` on Linux ([[lib/std/platform.my]], [[lib/std/platform_aarch64.my]]), `SwitchToThread` on Windows ([[lib/std/platform_windows.my]], as its `net_lock` does), nothing on wasm32, which has one worker ([[lib/std/platform_wasm.my]]: `yield_cpu` added beside `park`, nothing else there changed).

## Proposals (accepted 2026-11-16: D243)

1. **Yield, don't park** (built): the locks are held for a few loads and stores, never across a call that waits, so a waiter that gives its CPU up gets it again soon; parking on the lock's word would need a waiters' count and a wake on every release that saw one (a store more on each `give_lock`). Alternatives: park after a longer spin (a futex mutex); Windows only (`os.TARGET` folds), which leaves Linux's convoy, smaller there (its slices are short) but measured: 32 workers on 4 CPUs used 0.42 s of CPU, now 0.22 s.

## Evidence

- **Under Wine**, `SOCKETS 200 50` (tests/burn/test_windows.py) built with the library of `911d95b` and with this one, 16 workers, the machine idle (2026-11-16): 4.7 to 5.3 s and 13.6 to 16.1 s of user CPU before, 1.26 to 1.37 s and 0.52 to 0.61 s after (four runs each); 1 worker 1.7 to 1.9 s before, 1.8 to 2.1 s after; 4 workers 1.32 to 1.38 s before, 1.34 to 1.38 s after (user CPU 0.59 to 0.74 s, now 0.27 to 0.34 s).
- **Under load** (8 or 12 runs at once beside 4 or 8 CPU burners, 16 workers, BASE `983fcc3`'s program and this branch's in turn, a hang a run past 60 s): 7 of 60 hung before, 0 of 60 after; 24 of 60 before, 0 of 60 after (with [[MYLA-756]]'s fix in too).
- **Linux natively**, the same program: 4 workers 0.10 s and 0.09 to 0.11 s, 16 workers 0.12 to 0.15 s and 0.09 to 0.12 s, 32 workers 0.18 to 0.21 s (0.42 to 0.46 s of CPU) and 0.15 to 0.20 s (0.22 to 0.24 s of CPU), before and after.
- **Assembly**: for `selfhost/gen_main.my`, `examples/maps.my` and `examples/concurrency.my`, on `x86_64-linux`, `aarch64-linux`, `wasm32-wasi` and `x86_64-windows`, the library of `911d95b` and this one (both compiled from the same path) differ in `yield_cpu`, `take_lock` and the std.rt functions it is inlined into (`actor_enter`, `actor_leave`, `cancel_after`, `exec_find`, `exec_poll`, `exec_push`, `exec_steal`, `exec_yield_push`, `handle_take`, `poll_events`, `task_cancel`, `task_end`, `timer_add`, `timers_fire`, `wait_fds`, `woken_later`), and otherwise only in numbers: the positions of std.rt's lines (it grew) and the names of two of the loader's lambdas, numbered by where they are; `examples/maps.my` (no tasks) in one position record only.
