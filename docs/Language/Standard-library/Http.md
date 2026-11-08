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

The one-shot GET is `get`, and `fetch` is the same: the module was first written while the prelude's free `get(m, k)` took the name in the file being tested; maps have `m.get(k)` since [[MYLA-393]].

`request(method: str, url: str) -> Request` makes a request, which these methods change, each giving a new one:

| Method | The request with |
| --- | --- |
| `with_header(name, value)` | A header field added (after those it has) |
| `with_body(body)` | The body |
| `with_timeout(ms)` | A time limit for the whole exchange, redirects included (none by default): `TimedOut` then |
| `with_redirects(n)` | At most `n` redirects followed (5 by default; 0: the 3xx response is given back) |
| `with_decompress(on)` | `Accept-Encoding` sent and the body decoded (`true` by default), or neither |
| `with_limits(header_bytes, body_bytes)` | The response's limits: a head of 64 KiB and a body of 1 GiB by default. The body's counts the bytes received, before decoding: a small gzip body can decode to much more |

What a client sends, besides the request line and the request's own headers: `Host` (first, from the URL, unless the request has one), `Accept-Encoding: gzip, deflate` unless the request has one or doesn't decompress, `Connection: close` from `send` and the functions (not from a `Client`), and `Content-Length` when there is a body (or the method is `POST`, `PUT` or `PATCH`) and no framing of the request's own. A request with `Transfer-Encoding: chunked` has its body sent in chunks, with its `trailers`. No `User-Agent` is sent unless you add one.

What it does with the response:

- **Informational responses** (1xx but 101) are skipped.
- **Redirects** are followed: 301, 302, 303, 307 and 308 with a `Location`, resolved against the URL; a 303, and a 301 or 302 to a `POST`, becomes a `GET` without a body; another host gets no `Authorization` and `Cookie`. Past the limit it is `TooManyRedirects`. `response.url` is the URL the response came from.
- **Compressed bodies** (`Content-Encoding: gzip`, `x-gzip`, `deflate` as zlib or raw DEFLATE, several in turn) are decoded through [[Language/Standard-library/Compress]], and lose their `Content-Encoding` and `Content-Length` headers, as Go's client does. An unknown coding is left as it is.
- **Keep-alive.** A `Client` keeps the connection after a response that allows it (HTTP/1.1 without `Connection: close`, HTTP/1.0 with `Connection: keep-alive`, a body with a length). A request over a kept connection that the server had closed meanwhile (the connection ends, or is reset, before any byte of a response) is sent again, once, on a new connection, whatever its method.
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
| `workers` | 64 | How many connections are served at once, each by a task of its own; more wait in the listener's queue |
| `max_requests` | -1 | The requests answered before it returns (negative: no limit) |
| `max_header_bytes` | 65536 | A request's head (and its trailers) at most: 431 past it |
| `max_body_bytes` | 16777216 | A request's body at most (16 MiB): 413 past it |
| `keep_alive_ms` | 60000 | How long a connection takes requests (negative: as long as the client keeps it) |

The server runs `workers` tasks. Each accepts a connection on the listener, serves it request after request (keep-alive, pipelined requests too) and accepts the next one when it ends. Structured concurrency is why: no task outlives the scope that starts it, so a task started for each new connection would keep its frame until the server returned; a fixed pool keeps the memory bounded. The handler, and what it captures, is copied into each worker (values cross into tasks as copies, D89): keep large data out of its captures, or use few workers.

It stops when its task is cancelled (`task.cancel`, `task.timeout`: every wait in it ends), when `max_requests` requests were answered (it cancels its workers then, so the connections still open are closed), or when accepting fails for good. A connection is closed when the client closes it, after a request that says `Connection: close` (or an HTTP/1.0 one without `keep-alive`), and `keep_alive_ms` after it was accepted: a guard task shuts its reading then, which ends a wait for the next request (as the end of the stream does) and lets a response being written finish, and a response sent from a second before that time says `Connection: close`. So idle clients can't hold every worker for long. The guard is one task a connection; a `task.timeout` around each wait for a request would cost one a request, half the requests a second of a keep-alive client (measured: 10,500 against 21,000).

What the server writes: the status line (`HTTP/1.1`, the response's `reason` or the status's standard phrase), the response's headers but its framing, then `Content-Length`, or `Transfer-Encoding: chunked` with the trailers when the response has trailers and the client speaks HTTP/1.1; `Connection: close` when it closes, `Connection: keep-alive` to an HTTP/1.0 client it keeps. A `HEAD` gets the head alone, with the body's length (or the response's own `Content-Length`). 1xx, 204 and 304 have no body. A request with `Expect: 100-continue` gets `100 Continue` before its body is read. A request that can't be read is answered with its status and closed: 400 (malformed, no `Host` in HTTP/1.1), 413, 431, 501 (a transfer coding other than chunked), 505 (HTTP/2 and others); a response the handler made that can't be sent (a header with CR or LF) is a 500.

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

Reading follows RFC 9112. A line ends with CRLF or a bare LF; empty lines before a message are skipped; a header line is `name: value`, the name a token without space before the colon, the value trimmed of spaces and tabs; a line that begins with a space or a tab goes on the previous value (obsolete folding). The body: none for a `HEAD`'s response and for 1xx, 204 and 304; chunked when `Transfer-Encoding` ends with `chunked` (chunk extensions ignored, trailers kept); else `Content-Length` (repeated or listed values must agree); else, in a response, to the end of the connection, and none in a request. A message with both `Transfer-Encoding` and `Content-Length` uses the chunks, and its connection isn't used again. Writing always uses CRLF, and checks what it writes: a method or header name that isn't a token, or a value with CR, LF or NUL, is `BadHeader` (no header injection).

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
| `BadChunk` | A chunk size that isn't hex, a chunk not followed by its line end |
| `HeadersTooLarge`, `BodyTooLarge` | Past the limit |
| `TooManyRedirects` | More redirects than the request allows |
| `Decode(CompressError)` | A gzip or deflate body that doesn't decompress |

## How it works

One `Parser` reads every message. It is given the bytes that have come and takes what it can: whole lines of the head (a part of a line waits for the bytes after it), and a body's bytes as they come, appended to a builder, so it never slices a `str` ([[MYLA-390]]). The head's limit counts the line still unfinished, so a line that never ends is `HeadersTooLarge` too. `parse_request` and `parse_response` give it a whole text; a connection gives it each read of 64 KiB, keeping only the unfinished line between reads. The sync and the async forms differ only in how they read and write: the parser, the formatting, the redirects and the decoding are shared.

The server's workers wait on the one listener (the reactor watches it once, [[MYLA-346]]). With a request limit they count the requests in an actor and the server stops them; without one they count their own, as two actor calls a request cost a third of the requests a second.

Everything goes through `std.net`: a port to another system ([[Language/Standard-library/Net#porting-sockets-to-another-system]]) needs nothing here.

## Speed

Natively on x86-64, a server and a client in two programs on loopback, on a 4-core machine shared with other work, the best of six runs (the server with 4 workers; under the machine's load the runs ranged down to about 60 % of these):

| What | Speed |
| --- | --- |
| One keep-alive `Client`, 20,000 `GET`s of a 13-byte body, one after the other | 23,600 requests a second (42 µs each) |
| The same without `keep_alive_ms` (no guard task) | 25,500 a second |
| Four async clients in one program, 5,000 each | 23,300 a second |
| `fetch`, a connection each, 2,000 | 11,800 a second |
| A 100 MB body down (`send`, not decompressed) | 196 ms, 510 MB/s |
| A 121 MB body up (`post`) | 248 ms, 490 MB/s |

A body received costs the copies of a `str`: the reads into the builder, the builder's growth and its `build`; the raw loopback is five times as fast ([[Language/Standard-library/Net]]: 2.45 GB/s). A body sent is written as it is, after its head.

## Tests

The module's 161 cases (`build/myla test lib/std/http.my`) pass interpreted, natively, on aarch64 under qemu and on wasm32 under Node: the parsing of requests and responses (bare LF, folding, repeats, every framing and its errors, a message fed in pieces of 1 to 64 bytes), the formatting and its checks, the limits, chunked bodies, the content codings, redirects and URL resolution, keep-alive decisions, UTF-8 text.

`tests/burn/test_http.py` runs each program interpreted and built, natively and on aarch64 (qemu; loopback networking works there): the Myla server against Python's `http.client` (keep-alive on one connection, `HEAD`, a chunked upload, trailers, a large body), `urllib` and raw sockets (`Expect: 100-continue`, pipelining, bare LF, HTTP/1.0, the limits, malformed requests, no `Host`, a bad response header); the Myla client against Python's `http.server` (chunked, close-delimited, gzip and deflate bodies, redirects followed, left alone and looping, repeated headers, keep-alive, a kept connection the server dropped, a malformed status line, a body cut short, a bad chunk, a head and a body past the limits, timeouts, a refused connection, `https`, bad URLs), sync and async; a client and a server in one program; how long a connection is kept, idle and busy. On wasm32 it checks that an exchange and a server are `Unsupported`.
