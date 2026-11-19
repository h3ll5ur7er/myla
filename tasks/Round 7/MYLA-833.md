---
id: MYLA-833
title: "std.http: a response sent to a slow reader holds its worker; park it instead"
type: bug
status: review
priority: medium
labels: [std, http, runtime]
---
Found by [[Project/Review-2026-11-17]] (M8, "old"), left by [[MYLA-794]]. A worker that sends a response larger than the socket's buffer waits for the client in `write_async`, with `write_ms` (30 s by default) for each 64 KiB (`Link.send` in [[lib/std/http.my]]). A client that reads 64 KiB a second keeps within it, so 64 of them asking for an 8 MB response hold every worker of a default server for about two minutes: `repro-r6/runtime-http/http_slow_readers.py` (a normal request waits for the first worker freed). Reading was fixed the same way by [[MYLA-549]]: a request begun waits parked, holding no worker.

- [x] A response that doesn't go out at once waits parked for its socket to take more, holding no worker, as a request begun does; the bytes of the responses parked so stay within a room (what the workers held: `workers` responses), past which the worker sends it itself as now
- [x] A test: as many slow readers as workers, and a normal request answered at once

## What it needs

The lot ([[lib/std/rt.my]]'s `sock_park`, and the interpreter's lot in [[selfhost/interp.my]]) parks a socket until it is readable only. Parking for writability needs the watch's direction in `__sock_park` (its tag or a new argument: a primitive's shape changes, so the seeds are staged, D207) on both runners. Without it, the alternatives are a pool of sender tasks made with the workers (structured concurrency has no detached task: a fixed pool, as large as the slow readers it should outlast) or a task that tries every pending send without waiting every few milliseconds (a system call each per pending send per look).

## What changed

- **The primitive** (staged in `c984abf`): `__sock_park(lot, h, deadline, tag, events)`, `events` 1 until readable (as before) or 2 until the socket can send. Natively [[lib/std/rt.my]] `sock_park` adds the watch with that direction (the reactor already woke a send's watch, MYLA-346); interpreted the lot's look polls each parked socket for its own direction (`IParked.events`, `wake_parked`). The new argument is the shape change the task foresaw: a new argument, not a tag's bits, so the tag stays std.http's.
- **std.http** ([[lib/std/http.my]]): a worker sends what the socket takes at once (`Sending.go_on`: no actor call for a response that goes). What is left is put in the server's actor `Sends` by the connection and the connection parked with the tag SENDING until its socket can send (`park_sending`), its deadline `write_ms` from when its last 64 KiB began. The worker that takes it up (`serve_ready`) goes on inside the actor (`Sends.resume`: the pieces crossed into the actor once, when it was parked, and are sent in place; a file body is read on 64 KiB at a time), then counts the answer (the tally, MYLA-863), closes the file and serves the connection's next request, with the bytes of it the first worker had read (a pipelining client's, `unread`). A response whose time limit passed with less than 64 KiB gone is `TimedOut` and closed. The keeper looks for a parked response's writability (`poll_ms` takes `write_ms` now), `dropped` and `evict` close its file and give its room back, and a server that stops closes the files still parked.
- **The room**: at most `workers` responses wait parked (`Sends.room`), what the workers held before; past it the worker sends the rest itself as before (`Link.send_rest`, a task's wait with `write_ms`).

## Proposals

- **The room counts responses, `workers` of them** (built). Alternatives: *(a)* bytes, `workers` × `max_body_bytes` as D270 has for request bodies: a response has no size limit, so a room in bytes would say nothing of a response larger than it, and a file body holds 64 KiB, not its size; *(b)* no room: every slow reader parked, so memory grows with the slow readers (each a whole string body); *(c)* a pool of sender tasks (the task's alternative): a fixed pool still held by as many slow readers. Parked responses and the workers' own can hold `2 × workers` responses at once at most.
- **A parked response counts among the connections `max_connections` bounds**, as a request begun does; with deadlines of `write_ms` (30 s) it comes after idle ones (5 s) when the one whose time runs out first is closed.
- Proposed row: *"A response its socket doesn't take at once waits parked until the socket can send more, holding no worker, its time limit `write_ms` for each 64 KiB; at most `workers` responses wait so, past which a worker sends one itself ([[MYLA-833]], D269, D270)."*

## Evidence

- **Before** (`a995b75`, the test written first): `test_http.TimeLimits.test_slow_readers_hold_no_worker` (two slow readers of 8 MiB and two of a 3 MiB file, each with a 4 KiB receive buffer and not reading, beside a 4-worker server with `write_ms` 5 s) failed in both forms: the request on a connection of its own took 4.71 s (interpreted) and 4.71 s (built), the slow readers' `write_ms` less the test's 0.3 s.
- **After**: the three requests took 3.2 to 5.5 ms interpreted and 0.5 to 0.6 ms built (2026-11-19, `b7044ed`); each slow reader then got its whole response (8,388,608 `x` bytes, or the file's 3,145,851 bytes exactly) and a next request answered on the same connection.
- **Suites**: test_http (with the new test), test_router and test_reactor_scaling pass (30 tests, 312 s); std.http's cases 312/312 interpreted and `--native`, 316/316 with MYLA-841's and -842's under Wine; `poll_ms`'s cases changed for `write_ms`.
- **Targets**: `scripts/test-target.py aarch64-linux` passes test_http (321 s under qemu), test_router, test_reactor_scaling, test_net, test_fs and the primitives' suites (7 of 7). Under Wine (x86_64-windows), `test_idle_non_reading_and_slow_handled_connections` failed 3 of 3 (its built server's holders got the whole 8 MiB): the test waits until the server's process has one socket left (`/proc/<pid>/fd`) before its holders read, and Wine keeps a socket parked on the reactor (associated with the completion port) in its server, not always among the program's descriptors, so the count fell at once and the holders read while their responses waited parked, which is progress. A probe with the server's own log showed the parked responses dropped by the keeper at their time limit. Under Wine the test now waits 2 s instead (write_ms 300 and a keeper's look); BASE passed it 3 of 3 and this branch passes it 3 of 3 so. Windows has no `/proc`; what a parked send does there only CI's `windows-latest` job (the runner's `net/…` and `http/…` cases) shows.
- The room past which a worker sends a response itself has no burn test: one would need slow readers that keep reading within `write_ms` for longer than the test should take.
