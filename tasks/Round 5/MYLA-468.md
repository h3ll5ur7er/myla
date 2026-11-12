---
id: MYLA-468
title: "std.http: a silent connection holds a worker for `idle_ms`"
type: improvement
status: review
priority: medium
labels: [std, http, security, round-5]
---
Found by [[MYLA-422]]. The server serves each connection with one of `workers` tasks for as long as it is open (a fixed pool, as structured concurrency keeps a task started per connection until the server returns: [[Language/Standard-library/Http#the-server]]). [[MYLA-422]] bounds each wait (`idle_ms`, `read_ms`, `write_ms`), so a silent connection holds its worker for `idle_ms` at most, 5 s by default, where it was `keep_alive_ms`, 60 s. But `workers` clients that connect and say nothing, again every 5 s, still keep a default server from answering anyone: 64 sockets are enough.

```python
import socket, time
# against a default `http.serve_with` on `port`: no one else is answered
while True:
    held = [socket.create_connection(("127.0.0.1", port)) for _ in range(64)]
    time.sleep(4.5)
```

- [x] Wait for a connection's next request without holding a worker: the waiting connections on the reactor (one task watching many sockets, or a channel of ready connections the workers take from), a worker taken only once a request began; then `workers` limits the requests served at once, and a separate `max_connections` the sockets open
- [x] Or, smaller: when every worker is busy, an idle connection is closed at once (an accept waiting is seen through the listener's readiness)
- [x] A burn test: 64 silent connections, renewed, don't stop a default server
- [x] The owner's choice (2026-11-11): the first option, connections parked on the reactor (the second follow-up batch, lane R)
- [x] Burn tests: hundreds of silent kept connections don't delay a request; a parked connection's next request is served; `idle_ms` still closes it
- [x] std.http's throughput (one keep-alive client, four async clients) and the socket round trips before and after

The first follow-up built the second option (its text below, under *The first follow-up*); the owner chose the first on 2026-11-11, which the second follow-up built in its place.

## What changed (the second follow-up)

**Lots: sockets parked with no task (std.rt, a new primitive family).** A lot is a set of sockets parked on the reactor, each a watch with no frame in its descriptor's slot ([[MYLA-518]]'s table): `__sock_lot(n)` makes one whose readiness notifies the notifier `n` (a `std.task.Notifier`'s id); `__sock_park(lot, h, deadline, tag)` parks the socket `h` until it is readable, with a deadline (the parker's clock, negative for none) and a tag kept with it; when it becomes readable the reactor moves it to the lot's ready list and notifies the notifier once (one waiter woken, or a permit); `__sock_ready(lot)` takes the first ready one; `__sock_expired(lot, now)` takes one whose deadline passed (the parked are kept in the order of their deadlines, so this costs what it takes; `now` negative: the earliest, whatever its deadline); `__sock_tag(h)` reads the tag back; `__sock_lot_close(lot)` unwatches the rest and frees it. A lot is a handle (D181, kind 4). A close of a parked socket's descriptor puts it on the ready list (its parker finds it closed). The interpreter keeps its own lots, its parked sockets polled once a millisecond at most (the real clock, so `MYLA_TIME=virtual` doesn't stop them). The checker knows them as net primitives (`is_lot_primitive`); natively they are std.rt's functions by name, as the other socket primitives.

**std.http's server.** The listener and every connection waiting for a request, its first or its next, are parked on the server's lot. `workers` tasks wait on the lot's notifier; a ready socket wakes one. On the listener a worker accepts what waits without waiting (up to 64 connections, each parked at once with `idle_ms` and its `keep_alive_ms` end as its deadline, the end as its tag) and parks the listener again; on a connection it reads what the socket has, serves the request, the next one at once if the client sent it already (pipelining), and parks the connection again when nothing more has come. A keeper task (one a server, when `idle_ms` or `keep_alive_ms` limits a connection) closes the parked connections whose deadline passed every quarter of the shorter limit (10 ms to a second). The guard task of MYLA-422 and the first follow-up's look at the listener are gone: a request that comes and goes at once costs no task and no timer; a wait for more (a request in pieces, a response larger than the socket's buffer) is a `task.timeout` with `read_ms` (from the head's first byte, the head's end and each 16 KiB of the body) or `write_ms` (each 64 KiB). A server that stops closes every connection still open, parked or ready.

## Proposals (open decisions)

1. **`max_connections`, a new field of `ServerOptions`, default 1,024**: at most that many sockets parked (the listener among them while it is); past it, the parked connection whose time runs out first (with equal limits, the one parked longest) is closed for the new one, so silent clients can't lock others out, they only make quiet keep-alive connections reconnect sooner. An `EMFILE` accepting closes one too and accepts again 10 ms later. Alternatives: refuse new connections at the bound (stop accepting: `max_connections` silent clients would then stop the server, the attack the task is about); no bound, only `EMFILE`'s eviction (a server's descriptors are its limit then, which a default of 1,024 open files makes about the same). Recommended: as built.
2. **How connections are handed over: no acceptor task, the listener parked on the lot like a connection.** The worker it wakes accepts what waits and parks each new connection at once (its first request may not have come; when it has, the reactor reports it at the next look, a few µs), so one worker accepts a burst of 64 in one go and nobody waits on the listener: a connection wakes one worker, not all ([[MYLA-518]]). Alternatives: an acceptor task handing connections over by a channel (two channel operations a connection, a task more); every worker accepting on its own (the herd MYLA-518 removes, and a connection would hold its acceptor until its request came). Recommended: as built.
3. **What `workers` means: how many requests are served at once** (the handler's calls, a request being read and a response being sent), no longer how many connections are open. The default stays 64. Recommended.
4. **The time limits.** `idle_ms` and `keep_alive_ms` bound a parked connection (its deadline: the earlier of `idle_ms` from when it began to wait and its time's end), kept by the keeper to within its look; a parked connection taken up after its time's end is closed without reading; `read_ms` and `write_ms` bound a worker's waits as before, by `task.timeout` around the wait (a task each, only on a slow path), where a guard task beside each connection looked every quarter of the shortest limit. A response from a little before the time's end still says `Connection: close` (the end is the tag the connection is parked with). Alternative: a timer per parked connection in the runtime (its own heap entries, O(log n) each): exact to the millisecond, and more of the runtime; the keeper's look costs what it closes. Recommended: as built.
5. **Keep-alive accounting**: none beyond the above: a connection's `keep_alive_ms` runs from its accept, across its parkings (its tag), and requests per connection aren't limited (as before). The `max_requests` count stays the server's (`Tally`). Recommended: as built; a per-connection request limit (nginx's `keepalive_requests`) can come later as an option.
6. **The primitives' shape**: a lot notifies a `std.task.Notifier` the server makes, so a worker's wait is the notifier's (std.http calls `__waiter`, `__park` and `__woken` itself, `Notifier.wait`'s body, to spare two calls a request), and no new awaited primitive was needed (which would have touched the lowering, lane K's file). Alternative: an awaited `__sock_lot_wait(lot)` the reactor wakes directly. Recommended: as built unless a profile shows the notifier's path costs.

What remains: a client that sends a request's first bytes and then dribbles holds a worker for `read_ms` (20 s), as before; `workers` slow handlers still make new requests wait (by design: `workers` bounds the requests served at once).

## Evidence (the second follow-up)

`TimeLimits.test_kept_connections_wait_parked` in `tests/burn/test_http.py` (new), interpreted and built, against a 2-worker server (`idle_ms` 1,500): 200 connections each make a request and stay (kept), 100 more connect and say nothing; a request on a new connection must be answered within 1 s, every kept connection's next request on it must be served, and then every one of the 300 must be closed by the server within 3 s.
- Before (35b399e's `lib`, through a runner that points the test at it): `ConnectionResetError` in the first loop, interpreted and built (a kept connection's guard gave its worker up to the next connection and closed it).
- After: passes, interpreted and built.

Times (natively, a machine shared with three lanes): interpreted the 200 first requests 0.70 s, the request beside the 300 connections 5.4 ms, the 200 next requests 0.29 s, all closed 1.51 s after; built 0.055 s, 0.5 ms, 1.7 ms, 1.63 s.

`TimeLimits.test_silent_connections_renewed_do_not_stop_a_default_server` (64 silent connections renewed every 4.5 s against a default server, a request just after each of three renewals): 4.4 to 5.7 ms interpreted, 0.69 to 0.73 ms built, where it was 0.79 to 0.81 s with the first follow-up (two looks of a guard) and 4.30 s before it.
`KeepAlive`, the other `TimeLimits` cases, `MylaServer` (Python's clients), `OneProgram`, `NoReplay` pass unchanged. `tests.burn.test_reactor_scaling.Lots`: the primitives natively and interpreted, the same output. `build/myla test lib/std/http.my`: 222/222 interpreted, `--native`, `--target aarch64-linux` and `--target wasm32-wasi`.

Throughput (lane D's programs, natively, the server with 4 workers unless said, interleaved, the best of five, a 4-core machine shared with three other lanes, load 1.5 to 3.5):

| Server | One keep-alive client, 20,000 GETs | Four async clients | 2 workers: one, four |
| --- | --- | --- | --- |
| 35b399e (before) | 22,400 a second (median 17,700) | 27,400 (26,300) | 19,100, 31,300 |
| MYLA-518 alone | 28,600 (25,900) | 80,300 (71,900) | 32,200, 94,800 |
| MYLA-518 and MYLA-468 | 24,400 (23,300) | 84,700 (76,600) | 31,900, 95,700 |

So no regression against the base (an improvement, MYLA-518's), and the four clients as with MYLA-518 alone; the one keep-alive client on 4 workers is about a tenth below MYLA-518 alone (equal on 2 workers): its every request now goes through the lot (the reactor notifies, a worker wakes on the notifier and takes the socket) where a worker waited on its connection; with 4 workers on 4 shared cores the woken worker is more often a sleeping one. Sockets (8 connections × 20,000 round trips, 4 workers): 6.6 to 6.7 s before, 0.90 to 1.47 s with MYLA-518, 1.02 to 1.47 s with both.

Suites: `tests.burn.test_http` (10 tests, `HttpOnWasm` skipped natively), `test_reactor_scaling`, `test_net`, `test_time`, `test_concurrency_stress`, `test_scheduling`, `test_task_yield`, `test_timer_scaling`, `test_process` natively: 66 tests OK, 2 skipped; `test_http.TimeLimits`, `KeepAlive` and `test_reactor_scaling` with `MYLA_TEST_TARGET=aarch64-linux` (10 OK); `scripts/test-target.py wasm32-wasi tests.burn.test_http tests.burn.test_reactor_scaling` (`HttpOnWasm`, `Readers`). The checker's and the interpreter's new cases (`is_lot_primitive`, `net_primitive_sig`, `deadline_before`), `lib/std/rt.my` 22/22. The bootstrap reaches its fixed point.

## The first follow-up (superseded)

### What changed

A connection's guard, at a look where its connection waits for a request and has made no progress since the last look (it said nothing for a whole look, a second by default), polls the listener without waiting; when a connection waits to be accepted, it shuts its own connection's reading, and its worker closes it and accepts. A free worker would have taken the new connection at once, so a waiting one means every worker is busy. 64 silent connections renewed every 4.5 s no longer stop a default server: each gives its worker up a second or two after it was accepted when someone waits. A connection that waits gets in within one or two looks of a guard.

### Proposal (open decision)

**An idle connection gives its worker up when another waits to be accepted** (the task's second option), built. It keeps the server's design: a fixed pool of `workers` tasks, each serving one connection, and the guard of MYLA-422, which now also looks at the listener; nothing is added to a request (no actor call, no task, no new option), and it holds for any number of silent clients, as long as they send nothing.

Alternatives:
- *The waiting connections on the reactor, a worker taken only once a request began* (the first option): connection-holding tasks up to a new `max_connections`, one acceptor handing them over by a channel (every holder accepting itself would wake all of them for each connection: the reactor wakes every frame watching a descriptor), and `workers` tokens taken per request (two channel operations a request, which MYLA-422 measured as costly). It still lets `max_connections` silent clients (1,024, say, near the default descriptor limit) stop the server, and changes what `workers` means. Worth it with a reactor wait on many sockets at once in one task, which the runtime doesn't have.
- *A per-client limit* (connections per peer address): does nothing against clients from many addresses, and refuses many users behind one NAT.

What remains with the built option: a client that sends a request's first bytes and then dribbles holds a worker for `read_ms` (20 s), as with the first option; under more clients than workers, quiet kept connections are closed for new ones (a client reconnects, and idempotent requests are sent again).

### Evidence

`TimeLimits.test_silent_connections_renewed_do_not_stop_a_default_server` in `tests/burn/test_http.py` (it replaces MYLA-422's test that pinned the 3 to 9 s hold): 64 silent connections renewed every 4.5 s against a default server, interpreted and built; just after each of three renewals a request on a connection of its own must be answered within 3.2 s.

- Before (the test against bccc624's `http.my`): `[4.30, 4.30, 4.30]` s, interpreted and built (answered only at the next renewal, when the old connections closed).
- After: 0.79 to 0.81 s each.
- `tests.burn.test_http`: 9 OK (one skipped: `HttpOnWasm`) natively; `TimeLimits` (3 tests) with `MYLA_TEST_TARGET=aarch64-linux`. `build/myla test lib/std/http.my`: 221/221 interpreted and `--native`.
- Throughput (natively, interleaved with the base: [[MYLA-456]]'s evidence has the numbers): one keep-alive client's 20,000 GETs and four async clients' within the noise; the guard's poll of the listener happens only at a look that finds its connection idle and quiet, never on a request's path.
