---
id: MYLA-530
title: "std.http: a keep-alive request through the lot costs about a tenth more than a worker waiting on its connection"
type: improvement
status: backlog
priority: low
labels: [std, http, runtime, concurrency, round-5]
---
Found by [[MYLA-468]] (lane R of the second follow-up batch). A kept connection now waits for its next request parked on the server's lot: when it becomes readable the reactor puts it on the lot's ready list and notifies the lot's notifier, a worker parked on the notifier is queued, takes the socket (`__sock_ready`) and serves it. Before, the worker waited on the connection itself (`read_async`, a watch with its frame). With one keep-alive client against a server of 4 workers on a 4-core machine shared with other work, the parked way served about a tenth fewer requests a second (best of five: 24,400 against 28,600; medians 23,300 against 25,900); with 2 workers, or four async clients, the two are within the noise.

A round trip measured without std.http shows the same: one task serving a connection through a lot against one waiting in `read_async` (`lotrt.my` in lane R's scratchpad: `direct`, `lot1`, `watched`, and `yield` for the lot with the notifier's wait inlined), 4 workers: `direct` 12 to 27 µs, `lot1` 23 to 37 µs, but `watched` (a frame waiting in `__wait_socket`, then a blocking read) 24 to 51 µs, so the difference may be in how soon the woken frame runs, not in the lot. Sampling with gdb showed one worker blocked in `epoll_wait` (`exec_poll`) and the others asleep on the futex far more often on the lot's way, where on the direct way the workers caught the readiness in their spin's glances.

```myla fragment
// the worker's wait, as std.http has it
let h = __sock_ready(lot.id)
if h == 0 {
    let w = __waiter(lot.ready.id, -1i64, -1)
    await __park(w)
    let how = __woken(w)
}
```

- [ ] Find where the time goes (which worker runs the woken frame, how often a sleeping one is woken, the spin's length and glances against the client's round trip)
- [ ] If it is the notifier's hop: an awaited `__sock_lot_wait(lot)` the reactor wakes directly (a frame watching the lot), or a worker that lingers on its own connection while another worker waits on the lot
- [ ] Lane D's HTTP benchmark: one keep-alive client within the noise of a worker waiting on its connection
