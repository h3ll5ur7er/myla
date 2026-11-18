---
id: MYLA-863
title: "Windows: SOCKETS' 20th HTTP request once got no answer (net/sockets-and-children, 16 workers)"
type: bug
status: todo
priority: medium
labels: [platforms, windows, http, concurrency]
---
Found by [[MYLA-798]] on CI's real Windows (PR #81, run 44239811699, job 134584835555, head `2d96974`): `net/sockets-and-children` step 3 (`./prog.exe 200 50`, 16 workers), its third run, exit 2 after 201 s with nothing on the standard output and

```
ask 19: connection failed: Cancelled
still running after 200 s, tasks:
```

The same job's "Rates" step then ran the case 30 of 30 on 1, 4 and 16 workers (0.1 to 0.2 s each), and every earlier run on real Windows passed.

**What the output says** (MYLA-798, from the program and a reduced copy under Wine): `ask`, the task asking the program's own HTTP server 20 times on one kept-alive client, waited for its 20th answer (`/p19`) for the whole 200 s; the run's time limit then cancelled it, and a cancelled `get_async` reads `connection failed: Cancelled` (`HttpError.Io(IoError.Cancelled)`). The reduced copy (a server that accepts and never answers, the get inside `task.timeout`) prints exactly those two lines under Wine and on Linux. Every other task had ended (the empty list after `tasks:`). So the request was sent, or its connection made, and no answer came: the server (`http.serve_n(hl, 20, …)`, round 7's parked requests and eviction, [[MYLA-794]]) didn't answer it, or the client's or server's socket wasn't woken (std.platform's poller on the completion port, [[MYLA-706]], or std.rt's executor, whose queues changed in round 7, [[MYLA-791]]).

**What it isn't**: no code cancels by handle (no `CancelIo`/`CancelIoEx` anywhere in std or the runtime); MYLA-798's deferred-close limit closes, after 30 s, a socket handle that is still the program's own (it stays open until then, so its value can't have been reused), and this run never had a close wait 30 s before the 20th request.

- [ ] `SOCKETS` now gives each request 30 s (MYLA-798): a recurrence says `ask N: timed out after … ms, K answered before` and ends the run with its count; find which side lost the request (a server-side count of requests read, in the program, would tell)
- [ ] Reproduce: `windows-runner.py run --runs 30 --tally --only net/sockets-and-children` on Windows, or under Wine with load
- [ ] Fix, with a test
