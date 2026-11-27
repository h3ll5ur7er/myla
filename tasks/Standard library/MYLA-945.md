---
id: MYLA-945
title: "On Windows a server's 300 idle connections close about 1.5 s past idle_ms: test_kept_connections_wait_parked at its 4.5 s bound"
type: bug
status: todo
priority: low
labels: [http, windows, testing]
---
Found by [[MYLA-926]] step 2 (2026-11-24): on the native Windows runner, run 281 (`692f445`), `test_http.TimeLimits.test_kept_connections_wait_parked` (`server='built'`) took 4.532 s, its bound 4.5, from the last request to the end of all 300 connections (200 kept, 100 silent), where `idle_ms` is 3 s and the keeper looks every few milliseconds. It passed in runs 278 to 280 (with [[MYLA-933]]'s graceful close) and on Linux has a wide margin.

Not measured yet: where the 1.5 s go on Windows. Candidates: the 300 closes in turn under the net lock, each now a `CancelIoEx`, a `shutdown` and a `closesocket` ([[MYLA-933]]); the keeper's sweep; Python's 300 `end_of` reads on the runner.

- [ ] Measure on `windows-latest`: when the keeper closes each connection (the server's clock) against when the client reads its end
- [ ] Fix the cause if it is Myla's (a close taking milliseconds, the sweep), or give the bound the Windows margin its cause justifies, with the reason
