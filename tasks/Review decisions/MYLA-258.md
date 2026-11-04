---
id: MYLA-258
title: "Decision: the reactor — sleep, timers, timeouts and suspending I/O"
type: chore
status: review
priority: medium
labels: [decision, concurrency, runtime, io]
---
The design [[MYLA-230]] asks for before it is built (D107): with the runtime in Myla over a platform layer ([[MYLA-162]]), a reactor gives tasks `sleep`, timeouts, and reads and process waits that suspend the task instead of blocking its worker. What stands today: an idle worker spins, then parks on a futex (`exec_idle`); when every worker is idle and nothing is queued the program ends with "every task waits for another one" (`exec_stuck`); `std.io`'s reads and `std.process.run` block the worker that makes them; cancellation is a flag the task looks at (D96); a program without `async let` runs its async functions as ordinary calls (D90). The interpreter has its own ready queue, in the orders of D110.

## Questions

1. What a program writes: the API.
2. Where the reactor lives in the executor.
3. What the platform layer gives, here and on the other targets.
4. Timeouts and cancellation: what wakes a task suspended in the reactor.
5. How the interpreter models time, and what stays deterministic.

## Options

### 1. The API

- **A. Small, in `std.task` and a new `std.time`:** `await task.sleep(ms)`; `time.now_ms()` and `time.now_ns()` (a monotonic clock); `await task.timeout(ms, f)` running the async function value `f` as a child and giving `Some(result)`, or `None` when the time ran out first (the child cancelled, see 4). The suspending I/O keeps today's names: `std.io`'s `Reader` reads and `std.process.run` suspend the task when called in one, and block as now outside tasks.
- **B. A duration type** (`Duration`, `time.ms(5)`) from the start: clearer at call sites, more API before anything uses it.
- **C. Deadlines on every operation** (`read_line_until(deadline)`): precise, but every I/O function doubles.

### 2. The reactor's place

- **A. Idle workers poll (Go's netpoller shape):** the timers (a heap of `(deadline, frame)` under the queues' lock) and the watched descriptors live with the executor. A worker that finds no frame and sees timers or watched descriptors waits in the platform's poll (`epoll_wait`) with the nearest deadline as its timeout, one worker at a time (a flag); the others park on the futex as now. A push while a worker polls wakes it through an event descriptor in the poll set. Nothing changes for a program that never sleeps or waits on I/O: no poller, the same futex path.
- **B. A reactor thread:** one more thread that only polls and pushes the frames that became ready. Simpler to reason about; a thread more, and every wake-up crosses threads.
- **C. io_uring:** completions instead of readiness, fewer system calls; Linux-only, newer kernels, a much larger interface to port.

### 3. The platform layer's part

New functions of `std.platform` (Linux first): `clock_ns()` (monotonic), `sleep_ns(n)` (outside tasks), a poller (`poller_new`, `poller_watch(fd, token, readable)`, `poller_forget(fd)`, `poller_wait(timeout_ms, buf) -> count` giving the ready tokens, `poller_wake()`), and descriptors made non-blocking (`set_nonblocking(fd)`). On Linux: `clock_gettime`, `nanosleep`, `epoll_*`, `eventfd`, `fcntl`; a child process's end through `pidfd_open` (Linux 5.3), so a process wait is one more descriptor. On macOS kqueue gives the same readiness interface (`EVFILT_PROC` for a child); Windows' I/O completion ports are completion-based, which a readiness interface can sit on for pipes and timers (the port's job, [[MYLA-165]]).

### 4. Timeouts and cancellation

- **A. Cancelling wakes the reactor's waits:** a task suspended in `sleep` or a suspending read when it (or a task above it) is cancelled is woken at once; `sleep` returns early, a read gives what it has with the errno ECANCELED (`IoError.Other(125)`), so a cancelled child finishes promptly. `task.timeout` is then a race of the child against a sleeping sibling: whichever ends first cancels the other, and both are awaited before `timeout` returns (structured, D89). The cancellation stays a request (D96): a child computing without suspending still runs until it looks.
- **B. Only the flag (today's D96):** a sleeping or reading child is not woken; `timeout` returns only once the child ends on its own. Nothing new in the reactor, but a timeout around a blocked read never fires.

### 5. Time in the interpreter, and determinism

- **A. Real time in both:** the interpreter's sleeping tasks wait in deadline order on the real monotonic clock, and when every task sleeps it sleeps until the nearest deadline, as the native executor does. `time.now_*` read the same clock. Programs whose output depends on how long things take are not deterministic in either, as today with several workers; timers with distinct deadlines fire in deadline order, equal deadlines in the order they were set, in both.
- **B. A virtual clock in the interpreter:** time jumps to the nearest deadline when every task sleeps, so tests take no time and order exactly; the interpreter and native code then disagree on `now`, and a parity test can't mix sleeping with real work.
- **C. A for programs, B behind a switch** (`MYLA_TIME=virtual` for the interpreter, like `MYLA_SCHED`), for fast tests of timeout logic.

## Recommendation

**1A, 2A, 3 as listed, 4A, 5C.** A small API first (`sleep`, `now`, `timeout`; the I/O functions keep their names and suspend inside tasks), the duration type when a second user needs it; idle workers poll, so a program pays nothing until it sleeps or waits, and no thread is added; cancellation wakes reactor waits, which is what makes a timeout useful (a request still, D96); real time in the interpreter, with a virtual clock behind a switch for tests. `exec_stuck` then means: nothing queued, no timer, no descriptor watched. The order to build it: the clock, `sleep` and the timer heap with the poller (no descriptors yet, the event descriptor only); then `timeout` and cancellation waking waits; then suspending reads on pipes and standard input; then `std.process.run` on pidfds. Each with the interpreter's model and tests in both.

## Decision

Open: the owner's.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match ([[MYLA-230]])
