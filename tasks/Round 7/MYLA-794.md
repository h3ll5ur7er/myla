---
id: MYLA-794
title: "R7-5 HTTP: eviction under a slow-request flood (H7), body memory and slow uploads (M8), the glance cliff (M1)"
type: bug
status: review
priority: high
labels: [http, runtime, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "HTTP" (section 5). Files: `lib/std/http.my` (the server: connections, bodies, eviction; the router is [[MYLA-795]]'s), `lib/std/rt.my` (`exec_run`, `glance_every`). The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. No owner's decision. New tasks it files take ids 833–840.

- [x] **H7** (high, new): 1,024 connections that each send one byte, then 100 normal clients: 99 closed unanswered; a begun request is parked for `read_ms` (20 s), a new one for `idle_ms` (5 s), and eviction takes the one whose time runs out first. `repro-r6/runtime-http/http_evict_dos.py`. Reopens [[MYLA-549]]
- [x] **M8**: std.http keeps `max_connections × max_body_bytes` for bodies begun (100 × 4 MB: 598 MB, 17 MB before); an upload in 1,460-byte pieces costs 6.5× the CPU; 64 slow readers of an 8 MB response hold every worker for 30 s. `http_body_memory.py`, `http_slow_upload_cpu.py`, `http_slow_readers.py` (bodies and uploads done; the slow readers filed as [[MYLA-833]], below)
- [x] **M1** (new): D245's glance: a loopback ping-pong beside one task that only yields gives 499 round trips a second (98,942 with the 64-turn glance). A fix tried in a copy (`|| every >= GLANCE_TURNS`) gives 93,292 and keeps the latency gain. `rt_glance_pingbusy.my`, `rt_glance_candidate_fix.txt`. Reopens [[MYLA-755]]
- [x] [[MYLA-548]]'s follow-ups: `line_reader_with(s, 2147483647)` overflows at `net.my:1199`; `Signals { handle: 1 }.close()` starts listening
- [ ] Low: a FIFO in a served directory blocks a worker (with [[MYLA-795]]). Left to [[MYLA-795]]: the file is opened by `file_response`, the router's, which is that lane's

## What changed

**The glance (M1, `exec_run` and the new `glance_gap` in [[lib/std/rt.my]]).** A busy worker glances at the poller once a millisecond has passed since its last glance (D245, kept), or once `gap` turns have, whichever comes first. `gap` is 64 while glances wake frames (the glance of D124, every 64 turns) and doubles after each glance that wakes none, up to 1,048,576; so I/O beside short turns is woken within 64 turns again, and descriptors watched and quiet cost the millisecond's glances only. The review's candidate (`|| every >= GLANCE_TURNS`, a glance at each 64-turn read of the clock) recovers the throughput too, but costs a glance every 64 turns whatever it finds: under Wine, where a glance is a call to the Wine server, 8 tasks yielding 200,000 times beside a waiting accept took 1,441 ms against 81 ms (first run below). `exec_glance` gives what it woke through `exec_glanced`.

**Eviction (H7, [[lib/std/http.my]]).** Past `max_connections` the parked connection closed is the one that has waited longest since it last got on: one waiting for a request since it was parked, one whose request has begun since its head's first byte or the last 16 KiB of its body (`Reading.since`, set where its `read_ms` begins again, `Reading.step`). `Pending` keeps its handles in that order (a list with lazy deletion, compacted when it is twice as long as what it keeps), and `Pending.evicted` compares its oldest with the lot's: a connection waiting for a request whose deadline is within `idle_ms` of the oldest request's `since` waited longer (`__sock_expired(lot, since + idle_ms)`), else the request begun goes: it is forgotten and its socket closed (closing a parked socket makes it ready; the worker that takes it finds it closed and does nothing, as handles are never given twice).

**Bodies (M8).** The bodies the server keeps parked share `workers` times `max_body_bytes` (`body_room`: what the workers held before they were parked, 1 GiB by default); a body that would take them past it is answered `503 Service Unavailable` and its connection closed. Each next piece of a request waiting parked is read on inside `Pending` (`resume`): the worker sends the piece, and the request is copied out only once it is whole, or at a point where a worker goes on (its head asks for `100 Continue`). Before, each piece took the request out of the actor and put it back, two deep copies of the body so far. (A call of the actor's own `put` from `resume` copied its argument too: `resume` keeps the request itself.)

**[[MYLA-548]]'s follow-ups.** `LineReader.line` compares `max < n - pos - 1` instead of `pos + max + 1 < n`, which overflowed for the largest `int` ([[lib/std/net.my]]). `Signals.close` leaves a value whose handle is 1, which isn't a handle of the runtime's table but `__signal_listen`'s argument to begin listening ([[lib/std/signal.my]]).

## Proposals

1. **Eviction by the time since a connection last got on** (built), one order for connections waiting for a request and for requests begun. Alternatives: close a request begun before any connection waiting for one (a slow upload goes before an idle keep-alive connection); keep the lot's order (the one whose time runs out first) but give a request begun `idle_ms` as its order's deadline (the keeper then needs a second deadline); nginx's way, closing only reusable (idle) connections, refuses new ones under this flood. Suggested decision row: "**Past `max_connections`, std.http closes the parked connection that has waited longest since it last got on** ([[MYLA-794]]): since it was parked, for one waiting for a request; since its head's first byte or its body's last 16 KiB, for a request begun | The review of 2026-11-17, H7: with the one whose time runs out first, 1,024 one-byte requests (`read_ms`) made every new connection (`idle_ms`) the one closed"
2. **The room for bodies kept parked: `workers` times `max_body_bytes`, past it 503** (built). Alternatives: hold the worker past the room (the body read as before MYLA-549: the dribblers' hold on the workers comes back, after the room is filled); a room of its own in `ServerOptions` (a new field breaks every struct literal of it); count the declared length up front (an actor call for every body that doesn't come with its head, and a second to give it back). Suggested decision row: "**The bodies std.http keeps parked share `workers` times `max_body_bytes`** ([[MYLA-794]]): a body that would pass it is answered 503 and its connection closed | The review of 2026-11-17, M8: every parked connection kept its body, 100 of 4 MB took 598 MB where 2 workers had held 17 MB"
3. **The 64-turn glance comes back while it finds something** (built, D245 amended). Alternatives: the review's candidate (a glance every 64 turns always: the Wine cost above); a shared time of the last poll (D245's alternative, a runtime variable and a seed). Suggested amendment of D245: "… and every 64 turns while those glances wake frames, twice as many turns after each that wakes none (`glance_gap`, [[MYLA-794]]: the millisecond alone let a ping-pong beside a yielding task make 499 round trips a second)"

## Evidence

Tests first, each failing at BASE (fe30af6) and passing after:
- `test_reactor_scaling.BusyWorkers.test_round_trips_beside_tasks_that_only_yield` (new; a byte's round trips in 500 ms beside as many tasks that only yield as workers, more than 2,500): before 250 on 1 worker, 445 on 2. MYLA-755's `test_a_ready_socket_waits_a_turn_with_every_worker_busy` passes with it.
- `test_http.TimeLimits.test_one_byte_requests_filling_the_connections_give_way_to_new_ones` (new; 32 one-byte heads fill `max_connections` 32, then two waves of 10 clients): before, the newcomers closed unanswered (`b''`), interpreted and built.
- `TimeLimits.test_bodies_kept_parked_stay_within_the_room_for_them` (new; 2 workers, `max_body_bytes` 1,000,000, 12 bodies of 600,000 bytes waiting for their last): before 12 of 12 kept; after 3 kept and answered, 9 answered 503.
- `TimeLimits.test_a_body_dribbled_costs_its_pieces_not_its_size` (new; 4 connections, 200 single bytes each after 4 KB and after 4 MB, server CPU): before 0.27 s after 4 MB against 0.03 s after 4 KB; after, within twice.
- `lines_given` in [[lib/std/net.my]] (new cases; the largest `int` as the limit): before "integer overflow".
- `test_term.Signals.test_a_listener_built_by_hand_and_closed_catches_nothing` (new): before, the program outlived its SIGINT (killed after 10 s), interpreted and built.

The review's reproducers, BASE's library against this branch's, the same compiler (2026-11-17, at 11b0969, `build/myla build --stdlib`):
- `http_evict_dos.py` (defaults: 1,024 attackers, 100 clients a wave): before, every wave `{'closed': 99, 'answered': 1}` and a kept connection 1 of 5 answered, 1 of 1,024 attackers closed; after, every wave `{'answered': 100}`, the kept connection 5 of 5, 101 attackers closed (each newcomer one of theirs, while it was past the limit).
- `http_body_memory.py` (100 bodies of 4 MB, 2 workers, 4 threads): rss 574,568 kB and 106 descriptors before, 159,972 kB and 14 after (8 bodies kept, the rest 503); 200 bodies 1,222,920 kB against 281,172 kB. What is left is the reading of the bodies refused (each read as far as it came before its 503) and the allocator's lists per worker: over three rounds on one server 152, 284, 334 MB with 100 bodies and 300, 387, 417 MB with 400.
- `http_slow_upload_cpu.py`, 1 thread: 16,000,000 bytes in pieces of 1,460 every 2 ms, server CPU 6.52 s before, 0.63 s after (rss 49.6 MB, 17.1 MB); 4,000,000 bytes in pieces every 0.5 ms 0.23 s and 0.03 s; the same at once 0.01 s and 0.02 s.
- `http_body_dribble_cpu.py` (8 bodies, then single bytes every 2 ms each, 4 threads): after 15 MB, 136 % of a core before, 20 % after; after 1 MB, 87 % and 20 %.
- `http_slow_readers.py`: unchanged (a normal request waits until the slow readers' responses are sent): [[MYLA-833]].
- `line_reader_max_int.my` and `signals_forged_one.my`: their tests above.

M1's measurements (`rt_glance_pingbusy.my`, `rt_glance_busylat.my` and MYLA-755's `yields.my`: 8 tasks each yielding 200,000 times, plain and beside a task in `accept_async`; four libraries, the same compiler: BASE's, BASE's with the 64-turn glance of before D245, with the review's candidate, and this branch's at ab63339; interleaved, the median of 11 runs natively and of 5 under Wine 9.0; 2026-11-17, this 4-CPU machine shared with four lanes, load average 8 to 40, so the yields' columns scatter by about a fifth):

| natively | ping, 1 spinner, T=1 | T=4 | 8 spinners, T=1 | T=4 | yields T=1 | watched | yields T=4 | watched | busy wake-up µs, T=1 | T=2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BASE (D245) | 468 | 34,730 | 462 | 563 | 97 ms | 100 | 145 | 138 | 40,078 | 16,600 |
| 64 turns (D124) | 89,619 | 42,402 | 90,921 | 26,943 | 91 | 84 | 147 | 161 | 581,346 | 610,457 |
| candidate | 88,637 | 36,858 | 93,061 | 27,484 | 81 | 80 | 132 | 148 | 40,099 | 11,990 |
| this branch | 93,121 | 42,147 | 91,097 | 25,859 | 93 | 90 | 136 | 130 | 40,065 | 10,919 |

| under Wine | ping, 1 spinner, T=1 | T=4 | 8 spinners, T=1 | T=4 | yields T=1 | watched | yields T=4 | watched | busy wake-up µs, T=1 | T=2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BASE (D245) | 422 | 277 | 412 | 119 | 120 ms | 126 | 154 | 100 | 20,526 | 6,582 |
| 64 turns (D124) | 1,517 | 188 | 3,790 | 596 | 114 | 326 | 178 | 170 | 598,257 | 613,931 |
| candidate | 3,641 | 340 | 4,115 | 445 | 139 | 404 | 121 | 161 | 20,962 | 5,746 |
| this branch | 1,089 | 574 | 3,715 | 671 | 122 | 136 | 125 | 127 | 20,313 | 2,965 |

A first run at lower load (load average 1 to 4, the candidate's and the 64 turns' library the same, this branch's then the candidate's rule with a separate count of turns): under Wine "watched" at T=1 81 ms for BASE, 1,441 for the 64 turns, 1,463 for the candidate, 1,459 for that rule; this branch's (3 runs) 73 to 88 ms. Wine's loopback round trips are a few thousand a second whatever the glance: what a Windows machine gives, only the `windows-latest` job can show.

Suites: listed in the report of round 7's HTTP lane and below.
