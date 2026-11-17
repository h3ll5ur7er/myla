---
id: MYLA-794
title: "R7-5 HTTP: eviction under a slow-request flood (H7), body memory and slow uploads (M8), the glance cliff (M1)"
type: bug
status: todo
priority: high
labels: [http, runtime, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "HTTP" (section 5). Files: `lib/std/http.my` (the server: connections, bodies, eviction; the router is [[MYLA-795]]'s), `lib/std/rt.my` (`exec_run`, `glance_every`). The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. The owner's decisions it builds as the review recommends: none. New tasks it files take ids 833–840.

- [ ] **H7** (high, new): 1,024 connections that each send one byte, then 100 normal clients: 99 closed unanswered; a begun request is parked for `read_ms` (20 s), a new one for `idle_ms` (5 s), and eviction takes the one whose time runs out first. `repro-r6/runtime-http/http_evict_dos.py`. Reopens [[MYLA-549]]
- [ ] **M8**: std.http keeps `max_connections × max_body_bytes` for bodies begun (100 × 4 MB: 598 MB, 17 MB before); an upload in 1,460-byte pieces costs 6.5× the CPU; 64 slow readers of an 8 MB response hold every worker for 30 s. `http_body_memory.py`, `http_slow_upload_cpu.py`, `http_slow_readers.py`
- [ ] **M1** (new): D245's glance: a loopback ping-pong beside one task that only yields gives 499 round trips a second (98,942 with the 64-turn glance). A fix tried in a copy (`|| every >= GLANCE_TURNS`) gives 93,292 and keeps the latency gain. `rt_glance_pingbusy.my`, `rt_glance_candidate_fix.txt`. Reopens [[MYLA-755]]
- [ ] [[MYLA-548]]'s follow-ups: `line_reader_with(s, 2147483647)` overflows at `net.my:1199`; `Signals { handle: 1 }.close()` starts listening
- [ ] Low: a FIFO in a served directory blocks a worker (with [[MYLA-795]])
