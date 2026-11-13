---
id: MYLA-347
title: "std.http: an HTTP/1.1 client and server"
type: feature
status: done
priority: low
labels: [stdlib, net, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #48. Plain HTTP; HTTPS waits for TLS (roadmap #40).

- **Owns:** `lib/std/http.my`, `docs/Language/Standard-library/Http.md`
- **Needs:** [[MYLA-346]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] Requests and responses, headers, chunked bodies, keep-alive
- [x] A client (`get`, `post`, a request builder) and a server with a handler function, on the reactor
- [x] Gzip bodies through [[MYLA-344]]
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Done (2026-11-08)

`std.http` (`lib/std/http.my`, [[Language/Standard-library/Http]]), over `std.net` alone (no platform call, so a Windows port needs nothing here):

- **Messages.** `Headers` (names compared without ASCII case, kept in order and as written, repeats allowed: `get`, `get_all`, `has`, `has_token`, `add`, `set`, `remove`), `Request`, `Response` (`text()` as UTF-8 with U+FFFD for bad bytes, `bytes()`), bodies as `str` of bytes. One incremental `Parser` reads every message: CRLF or bare LF, empty lines before a message, obsolete folding, `Content-Length` (repeats must agree), chunked with extensions and trailers, close-delimited responses, no body for `HEAD`/1xx/204/304, `Transfer-Encoding` beside `Content-Length` (chunks win, the connection isn't reused). Limits on the head (the unfinished line counted too) and the body, `HeadersTooLarge` and `BodyTooLarge`. Writing always uses CRLF and refuses a method or name that isn't a token and a value or trailer with CR, LF or NUL (`BadHeader`: no header injection). Pure functions `parse_request`, `parse_response`, `format_request`, `format_response`, `reason`.
- **Client.** `fetch(url)` (the GET; see below), `post`, `send(request(…).with_header(…).with_body(…).with_timeout(ms).with_redirects(n).with_decompress(on).with_limits(h, b))`, a keep-alive `Client` (`send`, `get`, `post`, `close`), and every one async (`fetch_async`, `post_async`, `send_async`, `Client.get_async`, …). Redirects followed, 5 by default (`with_redirects(0)` gives the 3xx back), 303 and 301/302-after-POST become GET, credentials dropped across hosts. `Accept-Encoding: gzip, deflate` sent by default; gzip, x-gzip and deflate (zlib or raw) decoded through std.compress, the coding's headers then removed. A kept connection the server closed is retried once on a new one. The time limit covers the whole exchange (sync: each wait gets what is left; async: `task.timeout`). `https` is `Unsupported("https")`; on wasm32 everything is `Unsupported("sockets")`.
- **Server.** `serve(addr, handler)`, `serve_with(listener, options, async handler) -> Result<int, HttpError>`, `serve_n(listener, n, handler)`; `ServerOptions { workers, max_requests, max_header_bytes, max_body_bytes, keep_alive_ms }`. A pool of `workers` tasks (64) each serves a connection at a time, request after request (keep-alive, pipelining, `Expect: 100-continue`, HTTP/1.0 with and without keep-alive, trailers sent chunked to HTTP/1.1 clients, `HEAD`). Stopped by cancelling its task, or after `max_requests` (it cancels its workers then). Bad requests answered 400/413/431/501/505 and closed; a missing `Host` 400; a handler's response that can't be sent 500. A connection is kept `keep_alive_ms` (60 s): a guard task a connection shuts its reading then (so a wait for the next request ends, a response being written finishes), and responses from a second before say `Connection: close`.

Design choices to know: (1) **a pool of workers rather than a task spawned per connection**: structured concurrency keeps every child until its scope ends, so a task a connection would hold each finished connection's frame until the server returns; (2) the handler's captures are deep-copied into each worker (D89), so a large captured value costs `workers` times its size (the benchmark first ran out of memory with a 100 MB body captured by 64 workers); (3) **the keep-alive limit is a guard task a connection**, not a `task.timeout` around each wait for a request: that would halve a keep-alive client's requests a second (measured 10,500 against 21,000); (4) a server without a request limit counts its requests per worker, not in an actor: two actor calls a request cost about a third of the throughput.

**Names changed.** `http.get(url)` is `http.fetch(url)` (and `fetch_async`): the prelude declares a free function `get<K, V>(m: [K: V], k: K)` (`selfhost/checker.my`, `prelude_src`), so `pub fun get` in any module is "duplicate top-level declaration 'get'". A method may be `get` (`Client.get`, `Headers.get`). If the prelude's `get` goes (maps have `m.get(k)` in std.map), `get` can be added beside `fetch`. The idle timeout of the brief became `keep_alive_ms` (a connection's life, see above).

**Compiler bug found (native lowering).** An `await` inside a `match` nested in another `match`'s arm, where the inner scrutinee is the outer arm's binding, stops `myla build` with "internal error: worker can't be lowered to the IR: a function used as a value" (`selfhost/lower.my`, `name`); the interpreter runs it. Minimal:

```myla fragment
import std.task as task

enum Cause {
    Stop,
    Code(int),
}

async fun worker(r: Result<int, Cause>) -> int {
    match r {
        Ok(n) => { return n }
        Err(e) => {
            match e {
                Stop => {}
                Code(code) => {
                    print(code)
                    await task.sleep(1)
                }
            }
        }
    }
    return 0
}

#main
async fun main() {
    print(await worker(Err(Cause.Code(24))))
}
```

Worked around in `worker` and `serve_requests` by deciding outside the inner match (`accept_fate`, `answerable`).

## Evidence

- Test first, in part: the cases and test functions were written with the code; the first runs failed 3 module cases and the client burn test on expectations I had miscounted (a compressor message, a valid `\u{FF}`, a byte offset; Content-Length values), and natively the build failed on the lowering bug above, before the workaround.
- `build/myla test lib/std/http.my --stdlib lib`: 161/161 interpreted, `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node).
- `tests/burn/test_http.py` (5 tests, each Myla program interpreted and built): `MylaClient` against Python's `http.server` (37 checks: plain, chunked with a trailer, close-delimited, gzip, gzip without `Accept-Encoding`, gzip chunked, deflate, redirects followed, left alone and looping, 303 after POST, echoes of POST and PUT with repeated headers, HEAD, repeated `Set-Cookie`, 404, 300 KB, keep-alive on one connection, a server `Connection: close`, a dropped kept connection retried, the async forms, a malformed status line, a body cut short, a bad chunk, a head past 64 KiB, a body past its limit, timeouts sync and async and against a listener that never answers, a refused connection sync and async, `https`, two bad URLs); `MylaServer` against Python's `http.client` (six requests on one socket: GET, POST with a query and headers, trailers, HEAD, a chunked PUT, 200 KB), `urllib` (200 and 404), and raw sockets (100-continue, pipelining, bare LF, HTTP/1.0 closed and kept, `Connection: close`, a bad handler header → 500, a chunked upload with a trailer, no Host → 400; 400, 431, 413, 501, 505 and a bad length refused), 19 counted requests then `served 19`; `KeepAlive` (an idle connection closed by the guard, a busy one told `Connection: close`); `OneProgram` (three async clients and `serve_n` in one program, then a server stopped by `task.timeout`); `HttpOnWasm`. Natively: 4 pass, `HttpOnWasm` skipped; `MYLA_TEST_TARGET=aarch64-linux`: 4 pass; `MYLA_TEST_TARGET=wasm32-wasi`: `HttpOnWasm` passes, the four socket tests skipped (in the file: `_targets.py` isn't this task's).
- After `scripts/bootstrap.sh`: `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks`: 6 tests OK (the page's block runs interpreted and natively).
- Measured natively (two programs on loopback, server with 4 workers, 4-core machine shared with other lanes, best of six runs; runs ranged down to about 60 % of these): one keep-alive `Client`, 20,000 GETs of 13 bytes: 23,600 a second (25,500 without the keep-alive guard); four async clients in one program: 23,300 a second; a connection each (`fetch`): 11,800 a second; 100 MB down: 196 ms, 510 MB/s; 121 MB up: 248 ms, 490 MB/s (raw loopback through std.net: 2.45 GB/s).

## Review 2026-11-09

Not ready ([[Project/Review-2026-11-09]]): a chunk size that overflows `body_len + size` kills a checked or interpreted server and passes the body limit of a plain build (H7). The fix is in [[MYLA-422]].

- [x] The review's blocker, fixed with [[MYLA-422]]: H7, and M23 (the server's idle, read and write time limits, no replay of a POST, redirects resolved with dot segments)

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]].
