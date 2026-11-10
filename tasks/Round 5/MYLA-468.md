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
- [ ] Or, smaller: when every worker is busy, an idle connection is closed at once (an accept waiting is seen through the listener's readiness)
- [ ] A burn test: 64 silent connections, renewed, don't stop a default server
