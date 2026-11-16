---
id: MYLA-753
title: "Windows: a wait of the poller takes one batch of the port's packets, so a ready handle waits behind the backlog"
type: bug
status: review
priority: high
labels: [platforms, windows, concurrency]
---
Found by CI's `windows` job (run 43830453264, job 133174536402, windows-latest, 2026-11-16): `FAIL net/sockets-and-children (300.5 s): step 3 (./prog.exe 200 50): still running after 300 s; stdout b'', stderr b''`, the poller of [[MYLA-706]] (D236) on 16 workers; the three runs before passed (the case 8.0 s in master's run 43825708390).

- [x] Reproduced under Wine, and the cause found
- [x] A wait takes every packet queued, not one batch (`poller_drain`, [[lib/std/platform_windows.my]])
- [x] A regression test that fails before the fix (`test_windows.PollerBacklog`)
- [x] What the adversarial reading of the poller found beside it fixed (below)
- [x] The other causes of the hang filed: [[MYLA-754]], [[MYLA-755]], [[MYLA-756]]

## What hangs

`SOCKETS` (tests/burn/test_windows.py) runs an HTTP server in the program (`http.serve_n(hl, 20, handle)`) beside 200 echoed connections and 50 children, and asks it 20 times (`ask`). A hung run prints nothing because `main` waits for `serve_n`, which waits for its 20th request for ever: the first request failed with `connection failed: ConnectionReset` and the client went on to the next, so the server only ever saw 19. The reset is the server's: it parks an accepted connection until its request begins, for at most `idle_ms` (5 s), and its keeper closed this one, unread, after 5 s.

Traced (stderr lines from a copy of the library, Wine, 16 workers, the machine loaded): the client wrote its request at 4448675 ms, the server parked the connection at 4448767, and dropped it at 4454341 without it ever becoming ready. The poller's trace of another such run: the parked socket was armed at 4735102, its packet (the arm's "look at it now") was taken at 4740396, after the drop; a connect armed at 4734022 had its ConnectEx's end and its arm's packet taken at 4738855, 4.8 s later. In those 4.8 s the poller took 319 packets, in 5 waits of 64 (`ENTRIES`) each, 0.2 to 0.9 s apart, while 223 arms (each posting a packet) and the operations' ends queued more.

The cause: an I/O completion port is a queue in arrival order, every arm posts a packet and every operation's end queues another, and a wait (`GetQueuedCompletionStatusEx`) took at most 64. Under load more than 64 are queued, and a wait left the rest to later waits, one batch each, so a handle armed while ready (a request already there) was looked at only once the backlog in front of it had gone, seconds later. Linux's epoll has no such backlog: a wait gives the descriptors ready now, each once.

## What changed

- **`poller_drain`** ([[lib/std/platform_windows.my]]): after a wait whose call filled its 64 entries, the wait calls `GetQueuedCompletionStatusEx` again with no time limit and takes those too, until a call takes fewer than 64 (at most `DRAIN`, 64 calls, 4,096 packets, so a wait ends while other workers keep queuing). Each handle is still looked at once a wait however many of its packets came (`poller_take`'s mark), so the backlog's packets for one handle cost one look.
- **Found reading the wait, arm and close paths adversarially:**
  - `ws_closed`: a process's handle closed while its pool wait was registered set `F_CLOSED`, let the net lock go and waited in `UnregisterWaitEx` for the callback; a packet the callback posted then, taken by the waiting worker, freed the watched handle (closed, no packet due), and `ws_closed` then dropped and freed it again (and closed its event's handle value a second time). It now holds the watched handle across the unregister. Reachable when a child run is cancelled (`collect_async`'s kill, reap and close while the poller still waits for the child's end).
  - `ws_watch` found the watched handle, let the lock go and armed it under the lock again: closed meanwhile by another worker (a socket's copies reach the same one, D93), it could be freed. It now arms what the table holds under the lock, and a handle closed meanwhile is ready now, as one that isn't open is.
  - `__win_wait_posted` ([[selfhost/runtime_x86.my]]) set `posted` before reading the rest of its context: for a close that waited for its send (`ws_close_later`), `ws_later` frees the watched handle that holds the context as soon as `posted` is set, so the callback could read the function and the handle from freed memory. It reads its context first now. Windows only: the assembly for Linux, aarch64 and wasm32 is unchanged.
  - Checked and sound: a wake-up posted while nobody waits stays queued and the next wait returns at once; `NET_WAKE` is cleared only by the taker of the packet of no operation; a wake-up seen as due (`NET_WAKE` 1) whose packet is already taken is one the waiter returns for anyway; a level-triggered readiness that comes while a handle is armed again is a packet (a nudge whenever `F_NUDGED` is clear, which `poller_take` clears under the lock before it looks); a wake packet among a batch of handle packets is handled in `poller_take` as any other.
- **The exit path** (the coordinator's suggestion: `ExitProcess`' DLL detach): no hang reproduced in 5,600 runs of `time.minutes(4294967296i64)` built `--checked` (the Wine CI's timed-out case: the runtime error, then the exit), 16 at once, two CPUs burnt, and 3,000 runs of a task program ending by a runtime error, by `exit(3)` and normally while 32 tasks spin and sleep, on 4 and 16 workers (0 hangs, 2026-11-16). Left as it is; see the proposal.

## Proposals

1. **A wait drains the port** (built): every packet queued when it returns, at most 4,096. Alternatives: a bigger single batch (a larger `ENTRIES`: bounded the same way, but a backlog past it waits again); fewer packets (no nudge when an operation that will end is already in flight): fewer, but the backlog of ends remains, and the arm would have to look at the handle itself, outside the poller.
2. **The exit stays `ExitProcess`** (unchanged): no exit hang reproduced. If the runner sees one (a case whose output is whole and that doesn't end), `TerminateProcess(GetCurrentProcess(), code)` after `console_back`, as LLVM's `sys::Process::Exit` without clean-up and Chromium's immediate termination do, skips every DLL's detach; it loses nothing the runtime needs (its writes are synchronous, no C runtime buffers anything).

## Evidence

- **Test first**: `test_windows.PollerBacklog` (200 signalled events armed, a wake-up among them, one `poller_wait(p, 0)`) at BASE `983fcc3`: `FAIL poller_drains #1: expected (200, 200, 0), got (64, 64, 63)`; after the change `PASS`.
- **The hang reproduced**, BASE's sources: `net/sockets-and-children`'s program (`SOCKETS 200 50`) on 16 workers under Wine, 8 runs at once beside 4 processes burning a CPU each (this 4-CPU machine, shared with other work, load average 30 to 120), a hang a run past 60 s: 9 of 32 (2026-11-16, `983fcc3`). Every hang traced had its first request reset after the server's 5 s. Unloaded, 180 runs on 1, 4 and 16 workers hung none; with scheduling hiccups at the poller's race windows (a test-only copy of the library with `SwitchToThread` and `Sleep` there, not kept) 14 of 24 on 16 workers.
- **Before and after**, the same load, BASE's program and this branch's run in turn (2026-11-16): on 16 workers 9 hangs of 80 against 2 of 80 (the drain alone), then 10 of 100 against 1 of 100 (this branch); on 1 and on 4 workers 0 of 40 each, before and after. The hangs left are [[MYLA-755]]'s (no worker polled for 3.4 s, traced) and [[MYLA-754]]'s: with every worker busy and slow, the drain can't help a wait that doesn't come.
- **The cases**: lib/std/platform_windows.my's 159 interpreted and with `--target x86_64-windows` under Wine; `test_windows.PollerBacklog`.
- **The suites** (2026-11-16, this branch): `scripts/test-target.py x86_64-windows test_net test_http test_reactor_scaling test_process test_selfhost_codegen` 5 of 5 passed; `test_windows` and `test_windows_runner` 49 OK (1 skipped); `scripts/windows-runner.py build` and `run --wine --runs 3`: 148 passed, 12 skipped (as before: the console cases, `stdin/ready`, `tools/myla-build`) of 160; `scripts/test.sh fast` 1,003 tests, the one failure `test_embedded_std` before the bootstrap wrote the library's last comment; `scripts/check-seed.sh` passes (no seed changed).
- **The other targets unchanged**: BASE's `stage3` and this branch's give byte-identical assembly for `selfhost/gen_main.my`, `examples/maps.my` and `examples/concurrency.my` for `x86_64-linux`, `aarch64-linux` and `wasm32-wasi` (with this branch's library for both: the library's change is Windows' module only); for `x86_64-windows`, `examples/maps.my` differs in `__win_wait_posted`'s lines alone. The bootstrap's fixed point holds.
- **On CI's runner** (run 43852840522, PR #79 at this commit): `net/sockets-and-children` still hung on 16 workers, 300 s, nothing printed. So the drain wasn't enough there; [[MYLA-754]] and [[MYLA-756]] are fixed after it, and the case now says what failed instead of waiting for ever.

