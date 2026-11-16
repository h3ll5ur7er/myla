---
id: MYLA-756
title: "std.http's server drops a parked connection at its idle time without looking whether its request came"
type: bug
status: todo
priority: medium
labels: [http, concurrency]
---
Found by [[MYLA-753]]. The server parks an accepted connection until its request begins, for at most `idle_ms` (5 s), and its keeper closes the connections whose time ran out (`keeper`, `__sock_expired`, [[lib/std/http.my]]). It closes them unread, whether or not their request is there: when the wake-up for a parked socket comes late (a loaded program, [[MYLA-754]], [[MYLA-755]]), a request that came in time is reset. The client doesn't send a request again on a new connection (only on a kept one, `retryable`), so it fails with `connection failed: ConnectionReset`; in tests/burn/test_windows.py's `SOCKETS` the server (`serve_n(hl, 20, …)`) then waits for its 20th request for ever, which is CI's `net/sockets-and-children` hang (run 43830453264).

Traced under Wine ([[MYLA-753]]): the client wrote its request at 4448675 ms, the server parked the connection at 4448767 and dropped it at 4454341.

- [ ] The keeper looks at a connection whose time ran out before it drops it (`__poll`/`sock_poll` with no wait): one with input is served
- [ ] `SOCKETS` doesn't hang when a request fails: `ask` counts what it got, and the server's limit is what was asked (or the test says which request failed)
