---
id: MYLA-756
title: "std.http's server drops a parked connection at its idle time without looking whether its request came"
type: bug
status: done
priority: medium
labels: [http, concurrency]
---
Found by [[MYLA-753]]. The server parks an accepted connection until its request begins, for at most `idle_ms` (5 s), and its keeper closes the connections whose time ran out (`keeper`, `__sock_expired`, [[lib/std/http.my]]). It closes them unread, whether or not their request is there: when the wake-up for a parked socket comes late (a loaded program, [[MYLA-754]], [[MYLA-755]]), a request that came in time is reset. The client doesn't send a request again on a new connection (only on a kept one, `retryable`), so it fails with `connection failed: ConnectionReset`; in tests/burn/test_windows.py's `SOCKETS` the server (`serve_n(hl, 20, …)`) then waits for its 20th request for ever, which is CI's `net/sockets-and-children` hang (run 43830453264).

Traced under Wine ([[MYLA-753]]): the client wrote its request at 4448675 ms, the server parked the connection at 4448767 and dropped it at 4454341.

- [x] The keeper looks at a connection whose time ran out before it drops it (`__sock_poll` with no wait): one with input is served
- [x] `SOCKETS` doesn't hang when a request fails: what fails says so on stderr, and the program ends with 1 (or with 2 after 200 s, naming the tasks still running)

## What changed

- **`keeper`** ([[lib/std/http.my]], every target): a connection whose time ran out is looked at first (`__sock_poll(h, 1, 0)`); one with input (or its end, or an error) is parked again with no time limit, so the poller makes it ready at once and a worker serves it as any other: a request begun ([[MYLA-549]]'s `BEGUN` tag) keeps its tag and its pending part, and its worker answers 408 itself when its time has passed. One with nothing is dropped as before.
- **The tests' programs say what failed** (tests/burn/test_windows.py's `SOCKETS`, which scripts/windows-runner.py runs as `net/sockets-and-children`): each failed client, child and request on stderr with its error; a run whose tasks didn't all succeed ends with 1 instead of waiting for its servers; one still running after 200 s ends with 2 and names the tasks that hadn't ended (an actor of their ends); each server waits at most 200 s. tests/burn/test_http.py's `ONE_PROGRAM` (`net/http-one-program`) ends with 1 after printing its clients' lines when one of them failed. Their output when nothing fails is unchanged.

## Evidence

- **Test first**: `test_http.TimeLimits.test_a_request_that_came_while_the_server_was_busy` (Python's sockets: a quiet connection parked with `idle_ms` 400, a request that holds the program's one worker 700 ms, the quiet one's request sent meanwhile) failed three runs of three before the change, natively (`b''`: the connection closed unread; the interpreter served it), and passed three of three after (2026-11-16).
- **The suites**: `test_http`, `test_net` and `test_reactor_scaling` natively (39 tests, OK), with `--target aarch64-linux` and `x86_64-windows`; lib/std/http.my's cases 241/241.
- **The program's failure path**, under Wine: `SOCKETS 20 3` without its helper: `child 2: program not found` (and 0, 1), `40 of 43 right`, exit 1, in a second; with its helper `250 of 250 right, http 20, echoed true` on 1 and 16 workers, nothing on stderr.

Signed off by [[Project/Review-2026-11-17]] (done).
