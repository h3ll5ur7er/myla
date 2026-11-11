---
id: MYLA-468
title: "std.http: a silent connection holds a worker for `idle_ms`"
type: improvement
status: backlog
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

- [ ] Wait for a connection's next request without holding a worker: the waiting connections on the reactor (one task watching many sockets, or a channel of ready connections the workers take from), a worker taken only once a request began; then `workers` limits the requests served at once, and a separate `max_connections` the sockets open
- [x] Or, smaller: when every worker is busy, an idle connection is closed at once (an accept waiting is seen through the listener's readiness)
- [x] A burn test: 64 silent connections, renewed, don't stop a default server

The first option is left open: the second is built (below, a proposal).

## What changed

A connection's guard, at a look where its connection waits for a request and has made no progress since the last look (it said nothing for a whole look, a second by default), polls the listener without waiting; when a connection waits to be accepted, it shuts its own connection's reading, and its worker closes it and accepts. A free worker would have taken the new connection at once, so a waiting one means every worker is busy. 64 silent connections renewed every 4.5 s no longer stop a default server: each gives its worker up a second or two after it was accepted when someone waits. A connection that waits gets in within one or two looks of a guard.

## Proposal (open decision)

**An idle connection gives its worker up when another waits to be accepted** (the task's second option), built. It keeps the server's design: a fixed pool of `workers` tasks, each serving one connection, and the guard of MYLA-422, which now also looks at the listener; nothing is added to a request (no actor call, no task, no new option), and it holds for any number of silent clients, as long as they send nothing.

Alternatives:
- *The waiting connections on the reactor, a worker taken only once a request began* (the first option): connection-holding tasks up to a new `max_connections`, one acceptor handing them over by a channel (every holder accepting itself would wake all of them for each connection: the reactor wakes every frame watching a descriptor), and `workers` tokens taken per request (two channel operations a request, which MYLA-422 measured as costly). It still lets `max_connections` silent clients (1,024, say, near the default descriptor limit) stop the server, and changes what `workers` means. Worth it with a reactor wait on many sockets at once in one task, which the runtime doesn't have.
- *A per-client limit* (connections per peer address): does nothing against clients from many addresses, and refuses many users behind one NAT.

What remains with the built option: a client that sends a request's first bytes and then dribbles holds a worker for `read_ms` (20 s), as with the first option; under more clients than workers, quiet kept connections are closed for new ones (a client reconnects, and idempotent requests are sent again).

## Evidence

`TimeLimits.test_silent_connections_renewed_do_not_stop_a_default_server` in `tests/burn/test_http.py` (it replaces MYLA-422's test that pinned the 3 to 9 s hold): 64 silent connections renewed every 4.5 s against a default server, interpreted and built; just after each of three renewals a request on a connection of its own must be answered within 3.2 s.

- Before (the test against bccc624's `http.my`): `[4.30, 4.30, 4.30]` s, interpreted and built (answered only at the next renewal, when the old connections closed).
- After: 0.79 to 0.81 s each.
- `tests.burn.test_http`: 9 OK (one skipped: `HttpOnWasm`) natively; `TimeLimits` (3 tests) with `MYLA_TEST_TARGET=aarch64-linux`. `build/myla test lib/std/http.my`: 221/221 interpreted and `--native`.
- Throughput (natively, interleaved with the base on a loaded machine, see MYLA-456's evidence for the numbers): one keep-alive client's 20,000 GETs and four async clients' within the noise; the guard's poll of the listener happens only at a look that finds its connection idle and quiet, never on a request's path.
