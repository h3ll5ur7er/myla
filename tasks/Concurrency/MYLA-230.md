---
id: MYLA-230
title: "Sleep, timers, timeouts and suspending I/O on a reactor"
type: feature
status: review
priority: low
labels: [concurrency, runtime, io]
---
D107 ([[MYLA-212]]): waits for the runtime off assembly ([[MYLA-162]]). A reactor (epoll on Linux) in the runtime: `sleep`, timers and timeouts on awaits, and I/O in `std.io`/`std.process` that suspends the task instead of blocking the worker.

- [x] A design after [[MYLA-162]]: the reactor's place in the executor, the platform layer's part, how the interpreters model time — D124 ([[MYLA-258]])
- [x] The clock and `sleep`: `std.time` (`now_ms`, `now_ns`), `task.sleep`, the timer heap and the poller with its event descriptor only; `exec_stuck` with timers; the interpreter's sleeping tasks (real time, `MYLA_TIME=virtual`); tests in both
- [x] `task.timeout` and cancellation waking reactor waits
- [x] Suspending reads on pipes and standard input: async versions of `Reader`'s reads beside the blocking ones (D124 as refined: only an async function can suspend)
- [x] `std.process.run_async`, suspending, on pidfds

## Step 1: the clock and sleep (2026-11-04)

- `std.time` (`now_ns`, `now_ms`, on the primitive `__clock_ns`) and `std.task.sleep` (on the awaited primitive `__sleep`, lowered like `__yield`: the frame and a call of `myla___sleep`, then a suspension). Natively `sleep_frame` puts the frame on the timers, a heap by deadline and order under a lock; `exec_run` fires the timers that passed (queued so the earliest runs first under each order) before it looks for a frame; an idle worker that sees timers claims the poll (`__exec_polling`, one at a time) and waits in `std.platform`'s poller (epoll with an eventfd) until the nearest deadline or a push (`exec_pushed` and a new timer write the eventfd); `exec_stuck` only without timers. Without tasks `await __sleep(ms)` is the blocking `__sleep_ns`.
- The interpreter keeps its sleepers in a list: before each turn the ones whose time came are made ready (earliest first, as natively), and with no task ready it waits for the earliest, sleeping on the real clock or moving `MYLA_TIME=virtual`'s; once a task fails, every sleeper wakes so the others stop at once (D97).
- `tests/burn/test_time.py`: deadline order on 1 and 4 workers and in both orders, natively and in the interpreter on both clocks; 200 sleepers beside a computing task (all wake; in deadline order exactly with the virtual clock); a ten-second sleep in no time on the virtual clock; a failure beside a ten-second sleeper ends the program at once in both.
- On real time a sleeper whose time came while other tasks ran may go on after a later one (the newest-first order lets a later batch run before an earlier one still queued); the virtual clock orders exactly. A program with tasks that never sleeps pays one load more per frame and push: the stress programs 0.1% to 1.7% more instructions (t12, the push-heavy one, the most).

## Step 2: timeouts, and cancelling wakes sleepers (2026-11-04)

- `task.timeout(ms, f)` runs `f` as a child and arms a deadline on it (`__cancel_after`, which takes the `async let`'s name as `task.cancel` does); after `await` the child, `__disarm` says whether the deadline had not fired: `Some(result)`, else `None`. Rather than a sleeping sibling, the deadline is a timer entry of its own (the task's first frame, tagged): firing cancels the task and makes its sleepers' (and its children's) time come, under the timers' lock; a child with a deadline is flagged (4), so its end takes the deadline off under that lock before its parent is woken (`task_end`, which `myla___finish` now jumps to), and nothing touches its frame after it is freed. Timer entries are four words now (`[time][seq][frame][cell]`).
- `task.cancel` wakes the child's sleepers the same way (when there are timers), and a sleep in a task already asked to stop takes no time, natively and in the interpreter (whose deadlines are records beside its sleepers, fired before each turn and dropped when their task ends).
- Tests (`tests/burn/test_time.py`): a child done in time gives `Some`, one asleep past the limit, one computing until it sees the request and one whose own child sleeps give `None` promptly, natively on 1 and 4 workers and in the interpreter (the computing one left out with the virtual clock, where time passes only when every task sleeps); a cancelled sleeping child wakes at once. The suite passes, the stress tests three times in a row.

## Step 3: reads that suspend the task (2026-11-04)

- `Reader`'s async versions (`fill_async`, `read_line_async`, `read_exact_async`, `read_to_end_async`) wait on the awaited primitive `__wait_readable(fd)` before a read that then doesn't block; a task asked to stop gets ECANCELED. Natively `myla___wait_fd(frame, fd)` (std.rt's `wait_fd`) watches the descriptor in the poller (`EPOLLIN | EPOLLONESHOT`, the frame as the token; one the poller can't watch, a regular file, is ready at once) and keeps `[fd][frame]` in `__watches` under the timers' lock; the polling worker queues the frames its events name (unless a cancel took them first), waits with no deadline when only descriptors are watched, and a worker too busy to poll glances at the poller every 64 frames; a cancel unwatches and queues its tasks' waiting frames; `exec_stuck` also needs no descriptor watched. Without tasks the wait is nothing and the read blocks. The interpreter keeps waiting tasks beside its sleepers and polls their descriptors (`__poll`, no wait) before each turn, a millisecond at a time when nothing else is ready.
- `__wait_readable` is in `std.io`, which the compiler itself imports, so the seed learnt the primitive first (a seed from the sources without the new reads), as for `__syscall5`.
- Tests: lines fed 150 ms apart to a reader with `read_line_async` beside a ticker every 40 ms: on one worker the ticks come before the first line and between the lines, natively and in the interpreter (with the blocking `read_line` every tick waits for the input's end); a `timeout` of 50 ms around a read whose input comes two seconds later gives `None` at once on 1 and 4 workers and in the interpreter; standard input from a regular file is read at once.

## Step 4: a child process waited for without blocking the worker (2026-11-04)

- `std.process.run_async` (and `Command.output_async`): `__spawn` starts the child as `run` does (pipes, fork, exec, the exec's errno through a pipe closed on exec) without waiting, giving `[errno, pid, out, err, pidfd]` (`pidfd_open`: a descriptor readable when the child ends); one task then reads both pipes as either has bytes (`__wait_either`, a wait on two descriptors: the frame's two watch entries go together, so it is queued once), waits on the pidfd, and reaps the child (`__reap`: its code, or minus its signal). A task asked to stop kills the child (`__kill`), reaps it and gets ECANCELED. No `async let` in `std.process`: that would make every program importing it, the compiler too, a program with tasks.
- A race the tests found: the polling worker, counted idle, took a frame off the watches (or the timers) before queueing it, and another worker going idle in between saw nothing queued, watched or set, and ended the program ("every task waits for another one"; 11 of 60 runs on 4 workers). The frames on their way are now counted (`__exec_waking`), and the check reads the counts, then that, then the queues again: 0 of 60 runs on 4 workers, 0 of 30 on 16.
- Tests: a child that sleeps, writes to both streams and exits with 3 beside a ticker whose ticks all come first (on one worker; with the blocking `run` they wait for the child), 200 KB on each stream at once, a program that doesn't exist, a 50 ms limit around a child that would sleep five seconds (killed, no `sleep` left behind), and `run` unchanged; natively on 1 and 4 workers and in the interpreter.

## Where it stands (2026-11-04)

D124 is built: the clock and `sleep`, `timeout`, cancellation waking sleeps and reads, reads and child processes that suspend the task, natively on the executor's poller (epoll) and in the interpreter (real time, or `MYLA_TIME=virtual`). Left for later, as D124 said: a duration type; writes that suspend (a full pipe); sockets (no `std.net` yet).

