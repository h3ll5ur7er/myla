# std.http

An HTTP/1.1 client and server over [[Language/Standard-library/Net]] ([[MYLA-347]]). Plain HTTP only: an `https` URL is `Unsupported` until TLS. A body is a `str` of bytes, any bytes (D164). Everything that waits has an async form on the reactor; the server is async. On wasm32, which has no sockets, every exchange is `Unsupported("sockets")`, and the parsing and formatting work.

[TOC]

```myla
import std.http as http
from std.http import Request, Response
import std.net as net

fun handle(r: Request) -> Response {
    if r.path() == "/hello" {
        return http.response(200, f"hello, {r.query()[0].1}").with_header("Content-Type", "text/plain")
    }
    if r.method == "POST" {
        return http.response(201, f"got {r.body.len()} bytes")
    }
    return http.response(404, "no such page")
}

async fun client(port: int) {
    let base = f"http://127.0.0.1:{port}"
    var c = http.client()
    match await c.get_async(base + "/hello?name=Ada") {
        Ok(r) => print(f"{r.status} {r.header("Content-Type").unwrap_or("")}: {r.text()}")
        Err(e) => print(f"error: {e}")
    }
    match await c.post_async(base + "/upload", "some data") {
        Ok(r) => print(f"{r.status} {r.reason}: {r.text()}")
        Err(e) => print(f"error: {e}")
    }
    match await c.get_async(base + "/nowhere") {
        Ok(r) => print(f"{r.status} {r.reason}")
        Err(e) => print(f"error: {e}")
    }
    c.close()
    match await http.fetch_async("https://example.com/") {
        Ok(r) => print("fetched")
        Err(e) => print(f"error: {e}")
    }
}

#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("can't listen") }
    }
    let port = match l.local_addr() {
        Ok(a) => a.port
        Err(e) => { panic("no address") }
    }
    // a server that answers three requests and returns, beside the client
    async let served = http.serve_n(l, 3, handle)
    await client(port)
    match await served {
        Ok(n) => print(f"served {n}")
        Err(e) => print(f"server: {e}")
    }
    let c = l.close()
}
// output:
// 200 text/plain: hello, Ada
// 201 Created: got 9 bytes
// 404 Not Found
// error: unsupported: https
// served 3
```

## The client

| Function | Result |
| --- | --- |
| `get(url: str) -> Result<Response, HttpError>`, `fetch(url)` | `GET url`, over a connection of its own (`fetch` is the same, its first name) |
| `post(url: str, body: str)` | `POST url` with the body |
| `send(r: Request)` | The request `r`, over a connection of its own (`Connection: close`) |
| `get_async(url)`, `fetch_async(url)`, `post_async(url, body)`, `send_async(r)` (async) | The same, the task waiting |
| `client() -> Client` | A client that keeps its connection open between requests (keep-alive) |
| `Client`: `send(r)`, `get(url)`, `post(url, body)`, and `send_async`, `get_async`, `post_async` (async) | A request over the connection kept from the last one, when it goes to the same host and port and the server allowed it, else over a new one |
| `Client`: `close()` | The kept connection closed |

`Client`'s `exchange_async` and `follow_async` are the steps of its `send_async` (one exchange; the redirects), and `exchange`, `reusable`, `kept` and `finish` those of both sends (one exchange; the kept connection a request may use; the kept connection if it goes to the request's host; the connection kept or closed after a response, which is then made and decoded), public only because a method can't be private yet ([[MYLA-433]]); a program has no need of them.

The one-shot GET is `get`, and `fetch` is the same: the module was first written while the prelude's free `get(m, k)` took the name in the file being tested; maps have `m.get(k)` since [[MYLA-393]].

`request(method: str, url: str) -> Request` makes a request, which these methods change, each giving a new one:

| Method | The request with |
| --- | --- |
| `with_header(name, value)` | A header field added (after those it has) |
| `with_body(body)` | The body |
| `with_timeout(ms)` | A time limit for the whole exchange, redirects included (none by default): `TimedOut` then |
| `with_redirects(n)` | At most `n` redirects followed (5 by default; 0: the 3xx response is given back) |
| `with_decompress(on)` | `Accept-Encoding` sent and the body decoded (`true` by default), or neither |
| `with_limits(header_bytes, body_bytes)` | The response's limits: a head of 64 KiB and a body of 1 GiB by default. The body's counts the bytes received, before decoding: a small gzip body can decode to much more. A body is a `str`, so it has 2,147,483,647 bytes at most whatever the limit: a longer one is `BodyTooLarge` ([[MYLA-549]]). A negative limit is a runtime error naming it (D184) |

What a client sends, besides the request line and the request's own headers: `Host` (first, from the URL, unless the request has one), `Accept-Encoding: gzip, deflate` unless the request has one or doesn't decompress, `Connection: close` from `send` and the functions (not from a `Client`), and `Content-Length` when there is a body (or the method is `POST`, `PUT` or `PATCH`) and it isn't chunked. A request with `Transfer-Encoding: chunked` has its body sent in chunks, with its `trailers`, and no `Content-Length`; another transfer coding is `Unsupported`, as the client doesn't apply it. The framing is always the body's: a `Content-Length` of the request's own is replaced by the body's length, so the head can't disagree with what follows it; two `Host` fields, or one that isn't a host and port, are `BadHeader`, as the server refuses them ([[MYLA-549]]). No `User-Agent` is sent unless you add one.

What it does with the response:

- **Informational responses** (1xx but 101) are skipped. Their heads count against the response's head limit (`with_limits`), so a server that sends them without end gives `HeadersTooLarge` ([[MYLA-549]]).
- **Redirects** are followed: 301, 302, 303, 307 and 308 with a `Location`, resolved against the URL by `url.resolve` (RFC 3986, section 5.2, dot segments removed: [[Language/Standard-library/Url]]), with the URL's fragment when the `Location` has none (RFC 9110, section 10.2.2); a 303, and a 301 or 302 to a `POST`, becomes a `GET` without a body; another host gets no `Authorization`, `Proxy-Authorization` and `Cookie`. Past the limit it is `TooManyRedirects`. `response.url` is the URL the response came from.
- **Compressed bodies** (`Content-Encoding: gzip`, `x-gzip`, `deflate` as zlib or raw DEFLATE, several in turn) are decoded through [[Language/Standard-library/Compress]], and lose their `Content-Encoding` and `Content-Length` headers, as Go's client does. An unknown coding is left as it is. Each decoding step gives at most the request's body limit (`with_limits`, 1 GiB by default), as `max_output`: a body of a few kilobytes that stands for gigabytes (a decompression bomb, two codings too) is `BodyTooLarge`, not decoded whole ([[MYLA-472]]).
- **Keep-alive.** A `Client` keeps the connection after a response that allows it (HTTP/1.1 without `Connection: close`, HTTP/1.0 with `Connection: keep-alive`, a body with a length). A request over a kept connection that the server had closed meanwhile (the connection ends, or is reset, before any byte of a response) is sent again, once, on a new connection, if its method is idempotent (`GET`, `HEAD`, `OPTIONS`, `TRACE`, `PUT`, `DELETE`, RFC 9110 section 9.2.2): the server may have acted on the request before it closed, so a `POST` or `PATCH` is never sent twice (RFC 9112, section 9.3.1; [[MYLA-422]]). Before such a request goes over a kept connection, the client looks, without waiting, whether the server closed it meanwhile, and uses a new one if so; a server that closes it after that look gives the request's error (`Closed`, or `Io(ConnectionReset)`).
- **Time limits.** The sync forms give each wait (connecting, sending, receiving) what is left of the request's time; the async ones run the exchange under `task.timeout`.

## The server

| Function | Result |
| --- | --- |
| `serve(addr: SocketAddr, handler: (Request) -> Response) -> Result<(), HttpError>` (async) | Requests on `addr` answered by `handler`, with the default options, until the task is cancelled |
| `serve_with(l: TcpListener, o: ServerOptions, handler: async (Request) -> Response) -> Result<int, HttpError>` (async) | Requests on the listener `l` answered by the async `handler`, as `o` says; the number answered |
| `serve_n(l: TcpListener, n: int, handler: (Request) -> Response) -> Result<int, HttpError>` (async) | `n` requests answered, then it returns: the form for tests |
| `server_options() -> ServerOptions` | The defaults |
| `response(status: int, body: str) -> Response` | A response with the status's reason phrase and the body; `with_header(name, value)` and `with_trailer(name, value)` add to it |

`ServerOptions` has these fields:

| Field | Default | Meaning |
| --- | --- | --- |
| `workers` | 64 | How many requests are served at once, each by a task of its own; a connection waiting for its next request, or for the rest of one begun, holds none |
| `max_connections` | 1024 | How many connections are kept open between their requests at most (negative: no limit): past it, the kept one whose time runs out first is closed for the new one |
| `max_requests` | -1 | The requests answered before it returns (negative: no limit) |
| `max_header_bytes` | 65536 | A request's head (and its trailers) at most: 431 past it |
| `max_body_bytes` | 16777216 | A request's body at most (16 MiB): 413 past it, and past 2,147,483,647 bytes (a `str`'s most) whatever the limit |
| `keep_alive_ms` | 60000 | How long after it was accepted a connection takes new requests (negative: as long as the client keeps it) |
| `idle_ms` | 5000 | How long a connection waits for a request to begin, its first and each next one: then it is closed without an answer |
| `read_ms` | 20000 | How long a request's head may take from its first byte, and its body from the head's end, with that time again after each 16 KiB of it (a body comes at 800 bytes a second at least): then 408 and the connection closed |
| `write_ms` | 30000 | How long a response may take to send each 64 KiB of it: then the connection is closed |

Each time is in milliseconds; a negative one is no limit ([[MYLA-422]]).

The server runs `workers` tasks, and a keeper task when `idle_ms`, `keep_alive_ms` or `read_ms` limits a connection. A connection waiting for a request, its first or its next, is parked on the reactor: a socket watched with no task, no worker and no frame held, its deadline beside it ([[MYLA-468]]). So is a connection whose request has begun and whose next bytes haven't come: its parser, with what it read, is kept for the worker that takes it up when they come, and its deadline is the request's `read_ms` ([[MYLA-549]]). The listener is parked the same way. When a parked socket becomes readable (a request began, or the client closed it), the reactor puts it on the server's ready list and wakes one worker: on the listener the worker accepts what waits (up to 64 connections, each parked at once) and parks the listener again; on a connection it reads the request, calls the handler, sends the response, serves the next request at once if the client sent it already (pipelining), and parks the connection again. So `workers` is how many requests are served at once, and silent, idle or dribbling connections don't take any: 64 silent connections, renewed every 4.5 s, kept a default server from answering anyone before ([[MYLA-422]]), and so did 64 that each sent one byte, renewed every 19 s ([[MYLA-549]]); hundreds now don't delay a request. `max_connections` bounds the connections kept: past it, the kept one whose time runs out first is closed (its client opens another when it has a request). A failure to accept with too many open descriptors closes a kept one too, and the server accepts again 10 ms later. Structured concurrency is why the workers are a fixed pool: no task outlives the scope that starts it, so a task started for each new connection would keep its frame until the server returned. The handler, and what it captures, is copied into each worker (values cross into tasks as copies, D89): keep large data out of its captures, or use few workers.

It stops when its task is cancelled (`task.cancel`, `task.timeout`: every wait in it ends), when `max_requests` requests were answered (it cancels its workers then), or when accepting fails for good; the connections still open, parked or not, are closed then. A connection is closed when the client closes it, after a request that says `Connection: close` (or an HTTP/1.0 one without `keep-alive`), and when one of its time limits passes:

- **Waiting for a request** (`idle_ms`, and `keep_alive_ms` after the connection was accepted): the connection is closed without an answer, by the keeper, which looks every quarter of the shortest of the two and `read_ms` (from 10 ms to a second), so the limit is kept to within that. The parked connections are kept in the order of their deadlines, so a look costs what it closes. A response sent from a little before `keep_alive_ms` (a tenth of it, at most a second) says `Connection: close`, so a keep-alive client doesn't send a request that won't be read.
- **Reading a request** (`read_ms`): the head must come within it from its first byte; the body within it from the head's end, and again after each 16 KiB. Then the request is answered `408 Request Timeout` and the connection closed: by the worker that takes it up when more comes after the time, or by the keeper's look when nothing does. Between its pieces the request waits parked, so a client that dribbles its head (slowloris) or its body holds no worker ([[MYLA-549]]). `keep_alive_ms` doesn't cut a request that began: a slow upload is read whole.
- **The handler** has no time limit.
- **Sending a response** (`write_ms`): a client that doesn't read (or takes more than `write_ms` for each 64 KiB) has its connection closed, so it can't hold a worker for ever.

A worker reads what the socket has and sends what it takes without waiting; a request in pieces is parked between them, its parser kept in an actor of the server's by the connection (two actor calls each time it waits, none for a request that comes whole), and only a wait to send more (a response larger than the socket's buffer) is a task's with its time limit (`task.timeout`), so a request that comes and goes at once costs no task and no timer. The parking is std.rt's (`__sock_lot`, `__sock_park`, `__sock_ready`, `__sock_expired`, `__sock_tag`): natively the reactor's watches with no frame (one per socket, in the descriptor's slot, [[MYLA-518]]); interpreted the interpreter's own, its parked sockets polled once a millisecond at most.

What the server writes: the status line (`HTTP/1.1`, the response's `reason` or the status's standard phrase), the response's headers but its framing, then `Content-Length`, or `Transfer-Encoding: chunked` with the trailers when the response has trailers and the client speaks HTTP/1.1; `Connection: close` when it closes, `Connection: keep-alive` to an HTTP/1.0 client it keeps. A `HEAD` gets the head alone, with the body's length (or the response's own `Content-Length`). 1xx, 204 and 304 have no body. A request with `Expect: 100-continue` gets `100 Continue` before its body is read. A request that can't be read is answered with its status and closed: 400 (malformed, no `Host` in HTTP/1.1, two `Host` fields or one that isn't a host and port), 408 (not read within `read_ms`), 413, 431, 501 (a transfer coding other than chunked), 505 (HTTP/2 and others); a response the handler made that can't be sent (a header with CR or LF) is a 500.

## Messages

| Item | Meaning |
| --- | --- |
| `struct Headers { items: [(str, str)] }` | Header fields in order, repeats allowed, names kept as written. `Eq` |
| `headers() -> Headers` | None |
| `Headers`: `get(name) -> Option<str>`, `get_all(name) -> [str]`, `has(name)`, `has_token(name, token)`, `len()` | Names compared without ASCII case; `has_token` looks in the comma-separated values (`has_token("Connection", "close")`) |
| `Headers`: `add(name, value)`, `set(name, value)`, `remove(name)` | Changed in place (`var`): added at the end; every field of the name replaced by one, where the first was; every one taken out |
| `struct Request { method, url, version, headers, body, trailers, peer, timeout_ms, max_redirects, decompress, max_header_bytes, max_body_bytes }` | A request. The server's handler gets `url` as the target came (`/path?query`) and `peer`, the client's `SocketAddr`; the fields after `peer` are the client's |
| `Request`: `path()`, `query() -> [(str, str)]`, `header(name)`, `text()`, `bytes()` | The path without the query; the query's pairs decoded ([[Language/Standard-library/Url]]); a header's first value; the body as text and bytes |
| `struct Response { status, reason, version, headers, body, trailers, url }` | A response. `Eq` |
| `Response`: `header(name)`, `is_success()`, `text()`, `bytes()` | A header's first value; 200 to 299; the body as UTF-8 text (each byte that isn't valid UTF-8 replaced by U+FFFD) and as bytes |
| `parse_request(text) -> Result<Request, HttpError>` | A whole request: its line, headers and body (by `Content-Length`, or chunked with trailers) |
| `parse_response(text, method = "GET") -> Result<Response, HttpError>` | A whole response to a request with the method (a `HEAD`'s has no body): by `Content-Length`, chunked, or to the end of `text` |
| `format_request(r) -> Result<str, HttpError>` | The request as a `Client` sends it |
| `format_response(r) -> Result<str, HttpError>` | The response as the server sends it to an HTTP/1.1 client |
| `reason(status) -> str` | The standard reason phrase (RFC 9110), "" for a status it doesn't name |

Reading follows RFC 9112. A line ends with CRLF or a bare LF; empty lines before a message are skipped; a header line is `name: value`, the name a token without space before the colon, the value trimmed of spaces and tabs; a line that begins with a space or a tab goes on the previous value (obsolete folding). A value (or a reason phrase) with a NUL or a CR that doesn't end the line is refused, `BadHeader` (`BadStartLine`): another parser could take the CR for a line's end (RFC 9110, section 5.5). A request with two `Host` fields, or one that isn't a host and perhaps a port, is `BadHeader` (RFC 9112, section 3.2). The body: none for a `HEAD`'s response and for 1xx, 204 and 304; chunked when `Transfer-Encoding` ends with `chunked` (chunk extensions checked against RFC 9112's grammar, `;name` or `;name=value` with a token or a quoted string, and otherwise ignored; a chunk line past 4 KiB is `BadChunk`; trailers kept); else `Content-Length` (repeated or listed values must agree); else, in a response, to the end of the connection, and none in a request. A message with both `Transfer-Encoding` and `Content-Length` uses the chunks, and its connection isn't used again; in a request the `Content-Length` must still be a length (`Content-Length: zz` beside chunked is `BadLength`, 400, [[MYLA-549]]). Writing always uses CRLF, and checks what it writes: a method or header name that isn't a token, or a value with CR, LF or NUL, is `BadHeader` (no header injection).

## Errors

`HttpError` is a bare enum (D168), with `message()` and `Format`; it is `Eq` (two errors are equal when their messages are).

| Variant | Meaning |
| --- | --- |
| `InvalidUrl(str)` | A URL that doesn't parse, is relative, or has no host |
| `Unsupported(str)` | `https`, another scheme, a transfer coding other than chunked, an HTTP version other than 1.x, `sockets` (wasm32) |
| `Io(IoError)` | The connection failed: `ConnectionRefused`, `ConnectionReset`, … ([[Language/Standard-library/Net]]) |
| `TimedOut` | The time given ran out |
| `Closed` | The peer closed the connection before a message began |
| `Truncated` | The connection ended inside a message |
| `BadStartLine` | A request or status line that isn't one |
| `BadHeader` | A header line that isn't one; a header to send that would break the message |
| `BadLength` | A `Content-Length` that isn't a number, or two that differ |
| `BadChunk` | A chunk size that isn't hex, malformed chunk extensions, a chunk line past 4 KiB, a chunk not followed by its line end |
| `HeadersTooLarge`, `BodyTooLarge` | Past the limit (a body's as received, and as each decoding step gives it) |
| `TooManyRedirects` | More redirects than the request allows |
| `Decode(CompressError)` | A gzip or deflate body that doesn't decompress |

## How it works

One `Parser` reads every message. It is given the bytes that have come and takes what it can: whole lines of the head (a part of a line waits for the bytes after it), and a body's bytes as they come, appended to a builder, so it never slices a `str` ([[MYLA-390]]). The head's limit counts the line still unfinished, so a line that never ends is `HeadersTooLarge` too. A size from the network is compared with the room left under its limit (`size > max_body - body_len`), never added to what came before: a chunk size near the largest `int` is `BodyTooLarge` on every runner, where the sum trapped interpreted and with `--checked` and wrapped past the limit in a plain build (H7 of [[Project/Review-2026-11-09]], D184). `parse_request` and `parse_response` give it a whole text; a connection gives it each read of 64 KiB, keeping only the unfinished line between reads. The sync and the async forms differ only in how they read and write: the parser, the formatting, the redirects and the decoding are shared.

The server's workers wait on its lot, the parked listener and connections ([[MYLA-468]]): one notifier, notified once for each socket that became ready, so a connection wakes one worker. With a request limit they count the requests in an actor and the server stops them; without one they count their own, as two actor calls a request cost a third of the requests a second.

Everything goes through `std.net` and std.rt's socket primitives: a port to another system ([[Language/Standard-library/Net#porting-sockets-to-another-system]]) needs nothing here.

## Speed

Natively on x86-64, a server and a client in two programs on loopback, on a 4-core machine shared with other work, the best of six runs (2026-11-08, `8a56bc3`; the server with 4 workers; under the machine's load the runs ranged down to about 60 % of these):

| What | Speed |
| --- | --- |
| One keep-alive `Client`, 20,000 `GET`s of a 13-byte body, one after the other | 23,600 requests a second (42 µs each) |
| Four async clients in one program, 5,000 each | 23,300 a second |
| `fetch`, a connection each, 2,000 | 11,800 a second |
| A 100 MB body down (`send`, not decompressed) | 196 ms, 510 MB/s |
| A 121 MB body up (`post`) | 248 ms, 490 MB/s |

Since [[MYLA-518]] and [[MYLA-468]] (the reactor's watches by descriptor; connections parked between requests), the same programs, interleaved with the server before them on the same loaded machine, the best of five: one keep-alive client 24,400 a second (22,400 before), four async clients 84,700 (27,400 before); with 2 server workers 31,900 and 95,700 (19,100 and 31,300). Parking costs a keep-alive request about a tenth against a worker waiting on its connection (the server of [[MYLA-518]] alone: 28,600 and 80,300).

A body received costs the copies of a `str`: the reads into the builder, the builder's growth and its `build`; the raw loopback is five times as fast ([[Language/Standard-library/Net]]: 2.45 GB/s). A body sent is written as it is, after its head.

## Tests

The module's 225 cases (`build/myla test lib/std/http.my`) pass interpreted, natively, on aarch64 under qemu and on wasm32 under Node: the parsing of requests and responses (bare LF, folding, repeats, every framing and its errors, a message fed in pieces of 1 to 64 bytes), the formatting and its checks, the limits, chunked bodies, the content codings, redirects and URL resolution, keep-alive decisions, UTF-8 text.

`tests/burn/test_http.py` runs each program interpreted and built, natively and on aarch64 (qemu; loopback networking works there): the Myla server against Python's `http.client` (keep-alive on one connection, `HEAD`, a chunked upload, trailers, a large body), `urllib` and raw sockets (`Expect: 100-continue`, pipelining, bare LF, HTTP/1.0, the limits, malformed requests, no `Host`, a bad response header); the Myla client against Python's `http.server` (chunked, close-delimited, gzip and deflate bodies, redirects followed, left alone and looping, repeated headers, keep-alive, a kept connection the server dropped, a malformed status line, a body cut short, a bad chunk, a head and a body past the limits, timeouts, a refused connection, `https`, bad URLs), sync and async; against a raw Python server that logs each request, that a POST over a dropped kept connection reaches it once and a GET twice (`NoReplay`); a client and a server in one program; how long a connection is kept, idle and busy; the time limits against silent, dribbling, slow-uploading and non-reading clients and a slow handler, and 64 silent connections renewed every 4.5 s against a default server, a request answered within 3.2 s ([[MYLA-468]], `TimeLimits`); 192 requests begun (one byte, a head without its end, a body cut short) beside a default server and 200 dribbled heads beside two workers, a request answered at once, each request begun answered whole once it ends and each dribbler 408 ([[MYLA-549]]); a client that gets 30,000 `100 Continue` responses, `HeadersTooLarge`. The server runs built with `--checked` too, which a chunk size past `int32` killed before [[MYLA-422]]. On wasm32 it checks that an exchange and a server are `Unsupported`.
