---
id: MYLA-518
title: "The reactor's watches are a list scanned at every wait, and an event wakes every frame watching its descriptor"
type: improvement
status: backlog
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

- [ ] The watches kept per descriptor (a map, or an index in the handle table's entry), so a wait, a take and an event cost O(1) or O(frames on that descriptor)
- [ ] An event on a listening socket (or any descriptor many frames read) wakes one frame per readiness, not all of them, or the accepting tasks share one waiter (as `std.http`'s 64 workers do on one listener)
- [ ] A burn test: round trips beside 2,000 idle connections cost about what they cost alone; 2,000 accepting tasks take their connections in linear time
