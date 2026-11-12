---
id: MYLA-549
title: "R7 std.http: a request that has begun holds a worker; the client's redirect and write checks"
type: bug
status: in-progress
priority: high
labels: [std, http, security, round-6]
---
Work package R7 of [[Project/Review-2026-11-12]]. Files: `lib/std/http.my`, `tests/burn/test_http.py`. The other half of [[MYLA-468]], which declared it as what remains.

- [ ] **One byte per socket stops a default server** (high). 64 connections each send `G` and nothing more, renewed every 19 s: a normal request went unanswered for the 38 s watched (`python3 t_onebyte.py ./server` in `repro-r5/http/`, with `h.py` and `server.my`). The same with 200 header dribblers against 2 workers, even with `read_ms` 2,000: each freed worker takes the next dribbler (`t_park2.py`, case 3). A connection whose request has begun holds a worker for `read_ms`. Keep the parser with the parked socket and park again while a head is incomplete, so that a worker is held only for a complete head or an arriving body; or cap the workers that partial heads may hold (`serve_ready`, `read_request`)
- [ ] The client keeps `Proxy-Authorization` across hosts
- [ ] A redirect drops the original fragment when `Location` has none (RFC 9110, section 10.2.2: it is inherited)
- [ ] 30,000 `100 Continue` responses are skipped without a bound
- [ ] `format_request` writes two `Host` fields, or a `Content-Length` that disagrees with the body, when the caller set them (`hclient2.my`, `fmt.my`)
- [ ] The server ignores `Content-Length: zz` when `Transfer-Encoding: chunked` is present (200, connection closed)
- [ ] Body sizes are `int`: a `Content-Length` of 3000000000 is 413 and `BodyTooLarge` even with the limit at 2147483647. Document it, or count in `int64`
- [ ] An older leak: a program that starts a server and a client 12,000 times grows 555 bytes a round on one worker (`manyserve3.my`)
