---
id: MYLA-833
title: "std.http: a response sent to a slow reader holds its worker; park it instead"
type: bug
status: todo
priority: medium
labels: [std, http, runtime]
---
Found by [[Project/Review-2026-11-17]] (M8, "old"), left by [[MYLA-794]]. A worker that sends a response larger than the socket's buffer waits for the client in `write_async`, with `write_ms` (30 s by default) for each 64 KiB (`Link.send` in [[lib/std/http.my]]). A client that reads 64 KiB a second keeps within it, so 64 of them asking for an 8 MB response hold every worker of a default server for about two minutes: `repro-r6/runtime-http/http_slow_readers.py` (a normal request waits for the first worker freed). Reading was fixed the same way by [[MYLA-549]]: a request begun waits parked, holding no worker.

- [ ] A response that doesn't go out at once waits parked for its socket to take more, holding no worker, as a request begun does; the bytes of the responses parked so stay within a room (what the workers held: `workers` responses), past which the worker sends it itself as now
- [ ] A test: as many slow readers as workers, and a normal request answered at once

## What it needs

The lot ([[lib/std/rt.my]]'s `sock_park`, and the interpreter's lot in [[selfhost/interp.my]]) parks a socket until it is readable only. Parking for writability needs the watch's direction in `__sock_park` (its tag or a new argument: a primitive's shape changes, so the seeds are staged, D207) on both runners. Without it, the alternatives are a pool of sender tasks made with the workers (structured concurrency has no detached task: a fixed pool, as large as the slow readers it should outlast) or a task that tries every pending send without waiting every few milliseconds (a system call each per pending send per look).
