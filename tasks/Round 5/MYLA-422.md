---
id: MYLA-422
title: "P8 HTTP and URL: chunk sizes, timeouts, replay, resolution"
type: bug
status: review
priority: high
labels: [std, http, url, security, round-5]
---
Work package P8 of [[Project/Review-2026-11-09]] (wave A2). Files: `lib/std/http.my`, `lib/std/url.my`. Reopens [[MYLA-347]].

- [x] H7: a chunk size that overflows `body_len + size` is refused, checked and plain (D184)
- [x] M23: a write timeout, and an idle timeout separate from a connection's life (a client that never reads holds a worker; 64 idle connections stop a default server; `keep_alive_ms` cuts a slow upload)
- [x] M23: a dropped kept connection doesn't replay a non-idempotent request
- [x] `url.resolve` with dot segments, used by the redirects ([[MYLA-329]])
- [x] [[MYLA-329]]'s follow-up: `Url.to_str` keeps a port's leading zeros out (or refuses them)
- [x] Two `Host` fields, a NUL and a bare CR in a header are refused
- [x] [[MYLA-472]] (P9's finding, taken in at the integrator's request): a gzip or deflate body is decoded within the body limit, on P9's `max_output` (commit c3dc460 cherry-picked)

## What changed

- **H7 and the audit of sizes from the network (D184).** Every limit in the parser is compared with the room left (`size > max_body - body_len`, `used > max_head - seen`, the same for a close-delimited body), never with a sum: the body so far is within its limit, so the subtraction can't overflow, whatever limit `with_limits` gave. Content-Length and chunk sizes were already parsed in `int64` and refused past `int32` (`-2`). A chunk line past 4 KiB is refused whole too (before, only an unfinished one was), and chunk extensions must be RFC 9112's `;name[=token|quoted-string]` with optional whitespace (`5 junk` was taken as 5). `chunked()` and the request counters (`answered`, `total`, which a long-lived server could take past `int32`) no longer add past the largest `int`. `with_limits` with a negative limit is a runtime error naming it.
- **Fields.** A request with two `Host` fields, or a `Host` that isn't a host and port (`url.parse("//" + v)`), is `BadHeader` (400); a field value, a folded line or a reason phrase with a NUL or a bare CR is `BadHeader` (`BadStartLine`), in the parser, so `parse_request` and `parse_response` refuse them too.
- **M23, the server's time limits.** `ServerOptions` has `idle_ms` (5 s for a request to begin), `read_ms` (20 s for a head from its first byte; for a body from the head's end and again after each 16 KiB: 408) and `write_ms` (30 s for each 64 KiB of a response: the connection is shut both ways); `keep_alive_ms` now only ends the taking of new requests (the response from a tenth of it before, at most a second, says `Connection: close`) and cuts no request or response. The handler's time isn't limited. A guard task per connection polls every quarter of the shortest limit (10 ms to 1 s); the serving task tells it what it does by `notify_all` on the worker's notifier, whose generation the guard reads (four counts a phase, four more for progress), at most four lock-and-count calls a phase.
- **M23, the client.** Only `GET`, `HEAD`, `OPTIONS`, `TRACE`, `PUT` and `DELETE` (RFC 9110, 9.2.2) are sent again when a kept connection fails under them; before another method goes over a kept connection, the client reads it without waiting (`set_read_timeout(0)`, `read(1)`) and dials anew if the server closed it.
- **std.url.** `url.resolve(base, reference)` and `Url.resolve(r)`: RFC 3986, 5.2, strict, with `remove_dot_segments` linear in the path (the kept segments in a list, the input read by position). std.http's redirects use it. A port with a leading zero is `BadPort`. `Url` derives `Eq`.

## Evidence

- **H7, before:** the review's `bug_chunk_overflow.my` with this branch's base: `runtime error: integer overflow` at `std/http.my:1002` under `myla run` and `build --checked`, `error: connection closed inside a message` in a plain build (the limit passed, 2 GiB awaited). The new cases (`request_cases` #27, `limits`) failed the same way: `159/172 passed` with 13 failures, the overflow among them; `MylaServer` with the new raw requests and a `--checked` build: the interpreted and checked servers died (empty answers), the plain one timed out. **After:** `error: body too large` on all three runners; `MylaServer` passes interpreted, built and built `--checked`.
- **Fields, before:** the new cases for two `Host` fields, a `Host` with a space, a NUL and a bare CR in a value, a folded line and a trailer, a reason phrase with a NUL or a CR, `5 junk`, a NUL in an extension and an unterminated quoted extension all parsed (in the 13 failures above). After: refused.
- **URL resolution, before:** `resolve("http://h/a/b/c", "../d")` gave `http://h/a/b/../d` (the review's M23). After: the 42 examples of RFC 3986, 5.4 (normal and abnormal) are `url.my`'s `resolved` test, and `http.my`'s `resolve` cases add dot segments and a `Location` that doesn't parse; 10,000 `../` resolve to the root (100,000 take 7 ms natively; interpreted 300 KB of URL takes 6.6 s to *parse*, linearly: 3 µs a loop iteration in the interpreter).
- **Replay, before:** `NoReplay` (a raw Python server that logs each request) logged `POST /swallow` and `POST /swallow-async` twice, interpreted and built. After: once each, the dropped GET twice, and a POST after a kept connection the server closed goes on a new connection once.
- **Time limits, before** (the review's t_slow scenarios, `slow.py` in the lane's scratchpad, against the server built from the base): two clients that never read a 30 MB response held both workers (a request 3 s later timed out after 5 s); 64 silent connections against the default options: a request timed out after 8 s; a 3 s upload with `keep_alive_ms=1000`: `400 Bad Request`, "connection closed inside a message". **After:** the 64 silent connections: answered after 4.7 s; the upload: `200 OK` with its 30 bytes. `TimeLimits` (3 tests, interpreted and built): silent connections closed after `idle_ms` without an answer while a request is served; two non-reading clients of an 8 MiB response closed after `write_ms` and a request served; a 700 ms handler not cut by 300 ms limits, its connection kept; a 1.2 s upload past `keep_alive_ms` read whole and answered with `Connection: close`; a dribbled head answered 408 after `read_ms`; 64 silent connections hold a default server 3 to 9 s. Mutations: without the guard's shutdown of a sending connection, the first test hangs (2 errors); without the handler's mark, it fails (2 failures).
- **Speed** (natively, 4 workers, the machine loaded by four other lanes, interleaved with the base): 60,000 keep-alive GETs took 47 to 48 µs of the server's CPU each against 53 to 57 µs before (16,400 to 18,700 a second against 12,800 to 17,400); 100 MB down 608 to 664 ms against 724 to 848 ms. A first version kept the time in an actor (three calls a request): 125 to 142 µs a request, 5,700 to 11,700 a second; without its notifies the same, without its actor calls 49 to 58 µs — so the guard reads a notifier's generation instead.
- `build/myla test lib/std/http.my --stdlib lib`: 221/221 (219 before MYLA-472) interpreted, `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node); `url.my`: 162/162 on each (`myla test` has no `--checked`: the interpreter traps on overflow).
- `tests.burn.test_http`: 9 tests OK natively (one skipped: `HttpOnWasm`), with `MylaServer` also `--checked`. `MYLA_TEST_TARGET=aarch64-linux`: 9 OK (one skipped); `wasm32-wasi`: `HttpOnWasm` OK, 8 skipped.
- `scripts/test.sh fast`: 829 tests, the one failure `test_embedded_std` (expected until the seed commit). `scripts/test.sh` (all, after MYLA-472): 1,482 tests, 336 skipped, the one failure `test_embedded_std` again.

## Proposals (open decisions)

- **A port's leading zero is refused** (`http://h:080/` is `BadPort`). RFC 3986's grammar allows it, but `Url` keeps the port as an `int`, so `to_str` can't give it back. Alternatives: accept it and document that `to_str` writes the port without it (WHATWG URL and Python's `urllib` accept it); or keep the port's text in `Url`. Recommended: refuse, as built: what parses reads back, and two parsers can't disagree on such a port.
- **The default times**: `idle_ms` 5 s, `read_ms` 20 s, `write_ms` 30 s, Apache's `KeepAliveTimeout` 5 and `RequestReadTimeout header=20 body=20` with a minimum rate rather than nginx's 60 s between two reads. The time starts again after each 16 KiB of a body and each 64 KiB of a response, a minimum rate of 800 B/s up and 2.2 KB/s down. Alternatives: pure inactivity timeouts (any byte renews the time: a 1-byte-every-19-s client holds a worker for ever), or a total time per request (cuts large slow transfers).
- **Only idempotent methods are sent again**, after a look at the kept connection for the others. Alternative: send nothing again (simpler, more errors for keep-alive GETs), or let the request say it may be retried (a builder method), as Go's `Idempotency-Key` header does.
- **Which control bytes a value may hold**: NUL and a bare CR are refused (LF ends the line), the other C0 controls kept, as RFC 9110 allows. Alternative: refuse every control but HT, as Go's server does.
- **The guard reads `std.task`'s `Listener.gen`** (a field of a `pub struct`) and relies on `notify_all` counting the generation with no waiter: lane P5 owns `task.my`. Alternative: a public counter in `std.task` (`Notifier.generation()`), which P5 or the integrator could add; the read would then go through it.
- A request without `Host` is still refused only by the server (400), not by `parse_request`; [[MYLA-468]] is the worker-per-connection limit that remains.

## The owner's decision (2026-11-11)

The proposals stand as built (D189).
