---
id: MYLA-518
title: "The reactor's watches are a list scanned at every wait, and an event wakes every frame watching its descriptor"
type: improvement
status: review
priority: medium
labels: [runtime, concurrency, net, round-5]
---
Found by [[MYLA-456]] (lane D of round 5's follow-up batch). `lib/std/rt.my` keeps the frames waiting for a descriptor in one array, `__watches`, and looks through all of it under the timers' lock at every step: `watch_add` (`watched`, `watched_events`), `watch_take` (and `watched` again for each descriptor it took off), and `watchers_of` for each event. So a wait, a wake and an event each cost O(watches). And every frame watching one descriptor is woken by its event: N tasks in `accept_async` on one listener all wake for each connection, one accepts and N - 1 watch again, O(N²) for N connections.

Measured natively (2 workers): 20,000 round trips of 16 bytes on one connection took 142 ms beside no idle connection, 147 ms beside 500, 312 ms beside 2,000 (each read by a task waiting in `read_async`); accepting those 2,000 connections, with 2,000 tasks in `accept_async` on the listener, took about 16 s (0.2 s for 500).

```myla fragment
// N tasks each waiting in `l.accept_async()`, then N `net.connect`s: each
// accept wakes every waiting task
var hs: [async () -> int] = []
for i in 0..idle { hs.push(async () => await hold(l)) }
async let holders = task.all(hs)
```

The program is `watches.my` in lane D's scratchpad (`hold` accepts and then reads 16 bytes; `main` connects `idle` times, then times 20,000 round trips on one more connection served by another task).

- [x] The watches kept per descriptor (a map, or an index in the handle table's entry), so a wait, a take and an event cost O(1) or O(frames on that descriptor)
- [x] An event on a listening socket (or any descriptor many frames read) wakes one frame per readiness, not all of them, or the accepting tasks share one waiter (as `std.http`'s 64 workers do on one listener)
- [x] A burn test: round trips beside 2,000 idle connections cost about what they cost alone; 2,000 accepting tasks take their connections in linear time

## What changed

- **The watches by descriptor.** `__watches` is a table indexed by descriptor (`lib/std/rt.my`): each slot holds its watches in the order they came (a doubly linked list), how many wait to receive and to send, how many through the socket functions, what the poller watches it for now and whether the poller has it. A watch is one per frame and descriptor, `[fd][frame][events][next][previous][other]` (`other`: the frame's second watch, `wait_fd2`); the frame's task record holds its first watch | 3 (MYLA-456's `wait`), so a cancel finds it. Adding, taking, finding: O(1). `watch_take`, `watched`, `watched_events`, `watchers_of` and their scans are gone.
- **One frame per readiness.** `os.poller_event_ready(i)` (new in the three platform modules) says what event `i` is for (1 receive, 2 send, 3 both: an error or a hang-up). An event queues the first frame waiting for each readiness it reports and arms the descriptor again for the others: the poller's watch is one-shot and level-triggered, so a descriptor still ready (a second connection to accept, data the woken frame left) fires again at the next look, and the next waiter is woken then. A connection wakes one of N accepting tasks, not N.
- **Fewer system calls on the way.** A registration that fired stays and is armed again by the next wait (`poller_watch` and `poller_watch_socket` take `again`: `EPOLL_CTL_MOD` first, `ADD` when the poller has it no more), one call a wait instead of a `DEL` at the event and an `ADD` (failing, then `MOD`) at the next wait; a slot armed already for what a new waiter wants isn't armed again. The frames an event wakes are queued once the poll is given back (`push_woken`): a push while it was held wrote to the poller's wake-up descriptor to wake its holder, the pushing worker itself, and the next wait read it back.
- **An idle worker looks at the poller while it spins**, without waiting, every 512 of its 4,096 turns (`exec_glance`), when descriptors are watched: a descriptor armed again may be ready at once (the next accept), and a reply that comes while a worker spins was taken only once the spin was over. A busy worker still glances every 64 frames.
- **A close wakes the frames waiting on its descriptor** (`watches_closed`, from `__sock_close` and `__close`): their operation then fails with EBADF, as interpreted; natively they waited for good, and the next socket given the descriptor started with the old one's state. (The old scan-based code had the same hang.)
- wasm32's poller (`poll_oneoff` over at most 32 descriptors) is unchanged but for the new function and parameter: the table and the wake-one policy are std.rt's, shared by the three targets.

## Evidence

`tests/burn/test_reactor_scaling.py` (new, in `_targets.SUITES`; wasm32 runs `Readers` only, WASI having no sockets):

- `RoundTrips`: 1,000 round trips of 16 bytes on one worker (both sides in `read_async`/`write_async`), best of 5, alone and then beside 50,000 tasks in `accept_async` on a quiet listener, in one process. Before (35b399e's `lib`, through a runner that points the test at it): `309568 µs beside 50,000 waiting frames, 107426 µs alone` (fails; other runs 259 to 319 ms against 109 to 125). After: 3.9 ms and 3.9 to 4.0 ms.
- `Accepts`: the CPU time of 200 connections made one at a time (each awaited until taken, then 1 ms) beside 2,000 and 200 accepting tasks. Before: `0.521 s beside 2,000 accepting, 0.114 s beside 200` (fails; 0.49 to 0.56 against 0.165 in other runs). After: 0.072 against 0.048 s.
- `Closed`: a read waiting on a socket another task closes gets EBADF and the next socket with the descriptor reads (`error error 9 (Other(9)), read 3`). Before: it waited for good (timeout); interpreted it gave this line already.
- `Readers`: 500 tasks reading one pipe to its end each get woken in turn (every byte read once, every task ends), natively, aarch64 and wasm32.
- Passes natively, `MYLA_TEST_TARGET=aarch64-linux` (qemu) and `scripts/test-target.py wasm32-wasi`.

Lane D's programs (natively, 2 workers, a machine shared with three lanes): `watches.my` 20,000 round trips 1,318 ms beside no idle connection before (the round trip waited out an idle worker's spin), 1,450 beside 2,000; after 237 and 374 ms. Accepting 2,000 connections one at a time with 2,000 tasks waiting: 104 ms after; before 1.1 to 2.1 s with one burst (SYN retries once the backlog of 128 filled), the herd's cost varying with how many tasks were watching again when the next connection came.

Cost (lane D's benchmarks, interleaved with the base, 4 workers): 8 connections × 20,000 round trips (`read_async`/`write_async` both sides) 7.1 to 10.3 s before, 0.78 to 1.55 s after; one keep-alive client's 20,000 GETs 31,900 to 60,600 a second before, 41,000 to 52,400 after; four async clients 5,500 to 18,300 before, 7,400 to 40,500 after (noisy: a load of 2 to 5 from the other lanes).

Suites: `tests.burn.test_net`, `test_process`, `test_time`, `test_concurrency_stress`, `test_scheduling`, `test_task_yield`, `test_timer_scaling`, `test_http` natively (60 tests OK, 2 skipped); `lib/std/task.my` 36/36, `net.my` 98/98, `io.my` 30/30, `process.my` 48/48 natively and on aarch64, `task.my` and `net.my` on wasm32; `lib/std/rt.my` 17/17.
