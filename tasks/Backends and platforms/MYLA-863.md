---
id: MYLA-863
title: "Windows: SOCKETS' 20th HTTP request once got no answer (net/sockets-and-children, 16 workers)"
type: bug
status: in-progress
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

**Again on master, 2026-11-18** (`e6e1b9e`, the merge of PR #81, run 44258065912, the `windows` job's first step): step 3, run 1 (16 workers), `ask 19: timed out after 30002 ms, 19 answered before` and `269 of 270 right`. The same 20th request, the last of the run's 20, both times; that job's "Rates" step then ran the case 30 of 30 right. Twice so far on real Windows, where each `windows` job runs the case 33 times (3 in its first step, 30 in "Rates"); never on Linux (200 of 200 natively, this branch and master, 16 workers).

**What the last request points at:** the server is `http.serve_n(hl, 20, handle)`, which stops once its tally counts 20 answered (`serve_with` cancels its workers when `Tally.finished`) and closes the connections still open; the program never closes `hl`. A request counted twice, or an answer counted that the client didn't take as its own, stops the server one answer early: the client's last request then goes to a connection the server closes, and a retry on a new connection sits in the listener's backlog, which nothing accepts, until the client's 30 s. To find out: the server's count beside the client's (`serve_n`'s result, which the program prints only when both are right), and whether the client resends a request on a connection it found closed.

- [x] `SOCKETS` now gives each request 30 s (MYLA-798): a recurrence says `ask N: timed out after … ms, K answered before` and ends the run with its count; find which side lost the request (a server-side count of requests read, in the program, would tell)
- [ ] Reproduce: `windows-runner.py run --runs 30 --tally --only net/sockets-and-children` on Windows, or under Wine with load (SOCKETS itself not reproduced here, below; its mechanism reproduced at once by `test_http.ToTheLimit`; only the `windows` job runs real Windows)
- [x] Fix, with a test

## Again, on the owner's workstation: an answer lost after it was sent (2026-11-19)

Native Windows, 24 CPUs, `windows-runner.py run --runs 30 --tally --only net/sockets-and-children`, each bundle built from its commit:

| Bundle | 1 worker | 4 workers | 16 workers |
|---|---|---|---|
| master before PR #85 (`80bf233`, this task's fix in) | 30 of 30 | 30 of 30 | 29 of 30 (the miss ran to the 200 s limit) |
| PR #85 (`d7e65c1`, MYLA-833's parked sends) | 30 of 30 | 30 of 30 | 27 of 30 |

The full run of the bundle at `d7e65c1` had one more (step 3, run 2). Every miss on #85 printed `ask 19: timed out after 30003 ms, 19 answered before` / `269 of 270 right` / `the HTTP server: 20 handled, /p0@53248 … /p19@53248, 1 connections in turn, serve_n gave 20`: by this task's key, **20 handled with the client's 19, one connection, so an answer lost after it was sent**, not a request sent again. 1 of 30 against 3 of 30 doesn't tell whether MYLA-833 made it likelier. CI's 4-CPU `windows-latest` ran the case 39 times on `d7e65c1` without a miss (10 at 16 workers).

The fix above (an answer counts only once sent) holds: the server counted 20 because its 20th send went. What differs for the 20th is that `serve_n` stops right after it and closes the connection (`lot.close`), so the answer's bytes and the close follow each other closely. Where they can go:

- **The server's side:** the answer's bytes taken by an overlapped `WSASend` (`send_overlapped`, its bytes copied) and the socket closed before it ended: `sock_close` defers the close while `F_SENDING` (`ws_close_later`); a path that closes without it, or a flag already cleared, would drop the bytes.
- **The client's side:** the bytes arrive with the connection's end (FIN), and the client's wait on the completion port isn't woken for them (a lost wake on the poller with 16 workers on many CPUs), so it waits its 30 s.

To tell them apart, the next run's report should say whether the client's socket held the answer when it gave up: on a timeout, a non-blocking read of what is there (bytes: a lost wake; nothing: the server lost them). Or delay the server's close (sleep 100 ms after `serve_n`) and see whether the misses go: if they do, it's the send and the close close together.

- [x] The client's report says what its socket held: `SOCKETS`' `probe` looks at the kept connection once a request has waited 10 s (cancelled when the answer comes), and prints one of: `closed` or `its handle reused` (the client saw the end and asked again on a new connection), `not readable` (neither the answer nor the end came), `a receive took 0 bytes` (the end came without the answer), `a receive took N bytes, 'HTTP/1.1 200 OK'` (the answer came and the client wasn't woken). Each reading checked natively with a reduced program (a server that answers, says nothing, closes, and a raw connection given an answer's head or its end); a normal answer still takes 0 ms.
- [ ] A run of it on a Windows machine of many CPUs (CI's 4 CPUs haven't shown the miss in 39 runs)
- [ ] The cause fixed, with a case that fails before

## Evidence

**SOCKETS itself, not reproduced here** (BASE `3add216`, 2026-11-18): under Wine 9.0, 600 of 600 runs right (`./prog.exe 200 50` on 1, 4 and 16 workers, 50 runs each, 4 at once with a prefix each, load average 60 to 100); natively, 400 of 400 on 16 workers beside them.

**The hypothesis confirmed, in one of its forms: an answer counted that the client didn't get.** `serve_ready` counted a request answered (`Tally.answered`, and the worker's own count) whatever its send gave. A request whose answer couldn't be sent, its connection closed under it, was counted, so `serve_n`'s server reached its limit one request early; its connections closed as it stopped, and the kept-alive client's last request, sent again on a new connection (a GET on a kept connection the server closed, `exchange_async`), waited in the backlog of a listener nobody served any more. `test_http.ToTheLimit` (`TO_THE_LIMIT`): a client that asks for 8 MiB on a connection of its own and closes it unread once the handler has its request, then one kept-alive client sending exactly the server's limit of 20; the program prints both counts.

- BASE, natively: 60 of 60 wrong on 1, 4 and 16 workers, `ask 19: connection closed, 19 answered before` / `client 19 of 20, server 20` (one `ask 19: timed out`); under Wine 30 of 30 wrong, 24 of them `ask 19: timed out, 19 answered before`, the `windows` job's message on `e6e1b9e`; interpreted the same.
- **Fixed** (`lib/std/http.my`): an answer counts only once sent (`Tally.answered(sent)`: one that wasn't gives its place back), and the request after those being answered waits for them (`taken`: `Tally.take` says TAKE_LATER while the requests being answered would fill the limit; before, such a request was refused and its connection closed, so a client's request sent again after a failed answer was refused too). Then: 300 of 300 right natively (1, 4, 16 workers, under load), 90 of 90 under Wine, 90 of 90 under qemu-aarch64, and interpreted.
- In SOCKETS' run nothing should make a send fail; whichever the server counted that the client didn't get, the count no longer stops early for a failed send. **What only the `windows` job can show:** SOCKETS now serves with `serve_with` and a limit of 20 (as `serve_n` does) and a handler that notes each request's path and client port (`Served`): a run whose count is wrong, or that runs out of time, prints `the HTTP server: N handled, /p0@port …, K connections in turn, serve_n gave M` (or `still serving`). A request handled twice, on two connections, says the client sent it again; 20 handled with the client's 19 says an answer was lost after it was sent; 19 handled and `still serving` says the 20th never reached the server (the poller or the listener).

**Suites** (2026-11-18, this branch): `scripts/test.sh` 1,859 tests OK; `scripts/test-target.py` x86_64-windows 39 of 39 suites, aarch64-linux 38 of 39 then 39 (test_children_run_in_parallel, [[MYLA-745]]), wasm32-wasi 39 of 39; `tests.burn.test_windows` and `test_windows_runner` 73 tests OK under Wine; `scripts/windows-runner.py run --wine --runs 3`: 153 passed, 0 failed, 17 skipped of 170 cases (round 7's integration: 152 of 170, t15 failing); the bootstrap's fixed point, `scripts/check-seed.sh` and its Windows run.

## Proposals

Accepted by the owner on 2026-11-19 as D297.

- Built: `max_requests` counts answers sent; an answer that couldn't be sent gives its place back, and a request that comes while those being answered would fill the limit waits for them (1 ms looks at the tally). Alternatives: (a) count requests read, sent or not (BASE): a client that sends a request again after a failed answer finds no server; (b) refuse the extra request instead of waiting (`take`'s false): the request sent again after a failed answer was refused too, as `ToTheLimit` showed (`connection closed`).
