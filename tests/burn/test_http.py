"""Burn test: `std.http`, an HTTP/1.1 client and server (MYLA-347).

- the Myla server answers Python's `http.client` and `urllib` (keep-alive on
  one connection, `HEAD`, a chunked upload, trailers, a large body) and raw
  sockets (`Expect: 100-continue`, pipelining, bare LF line ends, HTTP/1.0,
  a malformed request, a head and a body past the limits, no `Host`);
- the Myla client talks to Python's `http.server` with a handler of this
  test's: plain, chunked (with a trailer) and close-delimited bodies, gzip
  and deflate ones, redirects (followed, left to the caller, a loop),
  repeated headers, keep-alive, a kept connection the server dropped, and
  the errors: a malformed status line, a body cut short, a bad chunk, a
  head past the limit, a body past it, a timeout, a refused connection,
  `https`, a URL that isn't one;
- the server's time limits (idle, read, write, keep-alive) against silent,
  dribbling, slow-uploading and non-reading clients and a slow handler,
  and 64 silent connections, renewed, against a default server (MYLA-422,
  MYLA-468);
- a client that sends a POST over a kept connection the server dropped
  only once, a GET again (MYLA-422);
- a Myla client and server in one program, three clients at once on the
  reactor.

Each Myla program runs in the self-hosted interpreter and built for the
test's target (`MYLA_TEST_TARGET`: aarch64 under qemu, whose loopback
networking works; on wasm32 there are no sockets, and `HttpOnWasm` checks
that a request and a server are `Unsupported` instead)."""
import gzip
import http.client
import http.server
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zlib

from ._native import (
    CAN_BUILD_NATIVE,
    SKIP_REASON,
    TEST_TARGET,
    Program,
    build_and_run_full,
    native_build,
    run_argv,
    selfhost_run,
    write_program,
)
from ._tools import STDLIB_ROOT, selfhost_tool

NO_SOCKETS = TEST_TARGET == "wasm32-wasi"
NO_SOCKETS_WHY = "WASI has no sockets (HttpOnWasm checks they are Unsupported)"

PRELUDE = r"""import std.http as http
from std.http import Request, Response, HttpError, Headers
import std.net as net
from std.process import args

fun int_of(s: str) -> int {
    var v = 0
    for c in s {
        v = v * 10 + (c - '0')
    }
    return v
}

fun show(r: Result<Response, HttpError>) -> str {
    return match r {
        Ok(resp) => {
            var sb = StringBuilder()
            let body = resp.text()
            if body.len() > 60 {
                sb.append(f"{resp.status} {resp.reason} ({body.len()} bytes)")
            } else {
                sb.append(f"{resp.status} {resp.reason} [{body}]")
            }
            for name in ["Content-Type", "Content-Encoding", "Content-Length", "Transfer-Encoding", "Set-Cookie", "Location"] {
                for v in resp.headers.get_all(name) {
                    sb.append(f" {name}={v}")
                }
            }
            for kv in resp.trailers.items {
                sb.append(f" trailer {kv.0}={kv.1}")
            }
            sb.build()
        }
        Err(e) => f"error: {e}"
    }
}

"""

# --- the Myla client against Python's http.server --------------------------------

CLIENT = PRELUDE + r"""
#main
async fun main() {
    let port = int_of(args()[1])
    let refused = int_of(args()[2])
    let silent = int_of(args()[3])
    let base = f"http://127.0.0.1:{port}"
    print(show(http.fetch(base + "/plain")))
    print(show(http.fetch(base + "/chunked")))
    print(show(http.get(base + "/close")))
    print(show(http.fetch(base + "/gzip")))
    print(show(http.send(http.request("GET", base + "/gzip").with_decompress(false))))
    print(show(http.fetch(base + "/gzip-chunked")))
    print(show(http.fetch(base + "/deflate")))
    print(show(http.fetch(base + "/redirect")))
    print(show(http.send(http.request("GET", base + "/redirect").with_redirects(0))))
    print(show(http.fetch(base + "/loop")))
    print(show(http.post(base + "/see-other", "form=1")))
    print(show(http.post(base + "/echo", "posted body")))
    print(show(http.send(http.request("PUT", base + "/echo?x=1").with_header("X-Custom", "a").with_header("x-custom", "b").with_body("put"))))
    print(show(http.send(http.request("HEAD", base + "/plain"))))
    print(show(http.fetch(base + "/cookies")))
    print(show(http.fetch(base + "/status/404")))
    print(show(http.fetch(base + "/big?n=300000")))

    // keep-alive: three requests over one connection, then one the server
    // closes after its answer, then one over a connection it dropped
    var c = http.client()
    var ports: [str] = []
    for i in 0..3 {
        match c.get(base + "/whoami") {
            Ok(r) => ports.push(r.body)
            Err(e) => ports.push(f"{e}")
        }
    }
    print(f"one connection: {ports[0] == ports[1] && ports[1] == ports[2]}")
    print(show(c.get(base + "/drop")))
    print(show(c.get(base + "/plain")))
    match c.get(base + "/whoami") {
        Ok(r) => print(f"a new connection after the drop: {r.body != ports[0]}")
        Err(e) => print(f"{e}")
    }
    c.close()

    // the async forms
    print(show(await http.fetch_async(base + "/chunked")))
    print(show(await http.post_async(base + "/echo", "async body")))
    var a = http.client()
    let first = await a.get_async(base + "/whoami")
    let second = await a.get_async(base + "/whoami")
    match first {
        Ok(f) => match second {
            Ok(s) => print(f"async keep-alive: {f.body == s.body}")
            Err(e) => print(f"{e}")
        }
        Err(e) => print(f"{e}")
    }
    a.close()

    // errors
    print(show(http.fetch(base + "/malformed")))
    print(show(http.fetch(base + "/truncated")))
    print(show(http.fetch(base + "/badchunk")))
    print(show(http.fetch(base + "/hugeheader")))
    print(show(http.send(http.request("GET", base + "/big?n=5000").with_limits(65536, 4096))))
    // a gzip bomb: 64 MiB of zeros in 64 KiB, past a limit of 1 MiB once
    // decoded (MYLA-472)
    print(show(http.send(http.request("GET", base + "/bomb").with_limits(65536, 1048576))))
    print(show(http.send(http.request("GET", base + "/slow").with_timeout(300))))
    print(show(await http.send_async(http.request("GET", base + "/slow").with_timeout(300))))
    print(show(http.send(http.request("GET", f"http://127.0.0.1:{silent}/").with_timeout(200))))
    print(show(http.fetch(f"http://127.0.0.1:{refused}/")))
    print(show(await http.fetch_async(f"http://127.0.0.1:{refused}/")))
    print(show(http.fetch("https://127.0.0.1/")))
    print(show(http.fetch("not a url")))
    print(show(http.fetch("http:///nohost")))
}
"""

CLIENT_OUT = """200 OK [plain text] Content-Type=text/plain Content-Length=10
200 OK [Wikipedia] Transfer-Encoding=chunked trailer X-Trailer=done
200 OK [until the end] Content-Type=text/plain
200 OK (160 bytes) Content-Type=text/plain
200 OK [not compressed] Content-Type=text/plain Content-Length=14
200 OK (160 bytes) Content-Type=text/plain Transfer-Encoding=chunked
200 OK [deflated text deflated text deflated text ] Content-Type=text/plain
200 OK [plain text] Content-Type=text/plain Content-Length=10
302 Found [] Content-Length=0 Location=/plain
error: too many redirects
200 OK [GET len=0 body= custom=] Content-Length=23
200 OK [POST len=11 body=posted body custom=] Content-Length=36
200 OK [PUT len=3 body=put custom=a,b] Content-Length=29
200 OK [] Content-Type=text/plain Content-Length=10
200 OK [cookies] Content-Length=7 Set-Cookie=a=1 Set-Cookie=b=2
404 Not Found [missing] Content-Length=7
200 OK (300000 bytes) Content-Length=300000
one connection: true
200 OK [dropped after this] Content-Length=18
200 OK [plain text] Content-Type=text/plain Content-Length=10
a new connection after the drop: true
200 OK [Wikipedia] Transfer-Encoding=chunked trailer X-Trailer=done
200 OK [POST len=10 body=async body custom=] Content-Length=35
async keep-alive: true
error: malformed request or status line
error: connection closed inside a message
error: malformed chunked body
error: headers too large
error: body too large
error: body too large
error: timed out
error: timed out
error: timed out
error: connection failed: ConnectionRefused
error: connection failed: ConnectionRefused
error: unsupported: https
error: invalid URL: not a url
error: invalid URL: http:///nohost
"""


class Handler(http.server.BaseHTTPRequestHandler):
    """The endpoints the Myla client is tested against."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def answer(self, status: int, body: bytes, headers=(), content_type: str | None = None):
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", content_type)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def body(self) -> bytes:
        n = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(n)

    def raw(self, data: bytes):
        self.wfile.write(data)
        self.wfile.flush()
        self.close_connection = True

    def chunked(self, chunks: list[bytes], headers=(), trailers=()):
        self.send_response(200)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for c in chunks:
            self.wfile.write(b"%x\r\n%s\r\n" % (len(c), c))
        self.wfile.write(b"0\r\n")
        for name, value in trailers:
            self.wfile.write(f"{name}: {value}\r\n".encode())
        self.wfile.write(b"\r\n")

    def do_HEAD(self):
        self.do_GET()

    def do_PUT(self):
        self.do_POST()

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self.body()
        if path == "/see-other":
            self.answer(303, b"", [("Location", "/echo")])
        else:
            self.echo(body)

    def echo(self, body: bytes):
        custom = ",".join(self.headers.get_all("X-Custom") or [])
        text = f"{self.command} len={len(body)} body={body.decode()} custom={custom}".encode()
        self.answer(200, text)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/plain":
            self.answer(200, b"plain text", content_type="text/plain")
        elif path == "/chunked":
            self.chunked([b"Wiki", b"pedia"], trailers=[("X-Trailer", "done")])
        elif path == "/close":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"until the end")
            self.close_connection = True
        elif path == "/gzip":
            if "gzip" in self.headers.get("Accept-Encoding", ""):
                self.answer(200, gzip.compress(b"compressed text " * 10), [("Content-Encoding", "gzip")],
                            content_type="text/plain")
            else:
                self.answer(200, b"not compressed", content_type="text/plain")
        elif path == "/gzip-chunked":
            data = gzip.compress(b"compressed text " * 10)
            self.chunked([data[:7], data[7:30], data[30:]],
                         headers=[("Content-Type", "text/plain"), ("Content-Encoding", "gzip")])
        elif path == "/deflate":
            self.answer(200, zlib.compress(b"deflated text " * 3), [("Content-Encoding", "deflate")],
                        content_type="text/plain")
        elif path == "/redirect":
            self.answer(302, b"", [("Location", "/plain")])
        elif path == "/loop":
            self.answer(302, b"", [("Location", "/loop")])
        elif path == "/echo":
            self.echo(b"")
        elif path == "/cookies":
            self.answer(200, b"cookies", [("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")])
        elif path == "/status/404":
            self.answer(404, b"missing")
        elif path == "/big":
            n = int(query.split("=")[1])
            self.answer(200, b"x" * n)
        elif path == "/whoami":
            self.answer(200, str(self.client_address[1]).encode())
        elif path == "/drop":
            # answered as if the connection stays, then closed
            self.answer(200, b"dropped after this")
            self.close_connection = True
        elif path == "/bomb":
            c = zlib.compressobj(9, zlib.DEFLATED, 31)
            data = b"".join(c.compress(bytes(1 << 20)) for _ in range(64)) + c.flush()
            self.answer(200, data, [("Content-Encoding", "gzip")])
        elif path == "/slow":
            time.sleep(1.0)
            self.answer(200, b"late")
        elif path == "/malformed":
            self.raw(b"HTTP/1.1 OK nope\r\n\r\n")
        elif path == "/truncated":
            self.raw(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nonly ten b")
        elif path == "/badchunk":
            self.raw(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nzz\r\n")
        elif path == "/hugeheader":
            self.raw(b"HTTP/1.1 200 OK\r\nX-Big: " + b"a" * 70000 + b"\r\nContent-Length: 0\r\n\r\n")
        else:
            self.answer(404, b"no such page")


class QuietServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # a client that gave up (the timeouts) is a broken pipe here
        pass


class PythonServer:
    """Python's threading HTTP server on 127.0.0.1, in a thread."""

    def __init__(self):
        self.server = QuietServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def free_port() -> int:
    """A port nothing listens on (bound, then closed)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_both(source: str, args=()) -> tuple[str, str, int]:
    """`source` in the self-hosted interpreter and built for the test's
    target, which must agree; their (stdout, stderr, exit)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = write_program(tmp, source)
        interp = selfhost_run(path, list(args))
        native = build_and_run_full(Program(path), args=list(args), argv0=path)
    assert interp == native, f"interpreter {interp!r} != native {native!r}"
    return interp


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipIf(NO_SOCKETS, NO_SOCKETS_WHY)
class MylaClient(unittest.TestCase):
    def test_against_pythons_http_server(self):
        server = PythonServer()
        # a listener that never accepts: a connection is made (the backlog),
        # and nothing ever answers
        silent = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        silent.bind(("127.0.0.1", 0))
        silent.listen(8)
        try:
            args = [str(server.port), str(free_port()), str(silent.getsockname()[1])]
            self.assertEqual(run_both(CLIENT, args), (CLIENT_OUT, "", 0))
        finally:
            silent.close()
            server.close()


# --- the Myla server against Python's clients --------------------------------------

SERVER = PRELUDE + r"""from std.io import println

fun handle(r: Request) -> Response {
    let path = r.path()
    if path == "/hello" {
        return http.response(200, "hello\n").with_header("Content-Type", "text/plain")
    }
    if path == "/echo" {
        var sb = StringBuilder()
        sb.append(f"{r.method} {r.version} body={r.body} len={r.body.len()}")
        for q in r.query() {
            sb.append(f" q[{q.0}={q.1}]")
        }
        for kv in r.headers.items {
            if kv.0.len() > 2 && (kv.0[0] == 'X' || kv.0[0] == 'x') && kv.0[1] == '-' {
                sb.append(f" h[{kv.0}={kv.1}]")
            }
        }
        for kv in r.trailers.items {
            sb.append(f" t[{kv.0}={kv.1}]")
        }
        let from_here = match r.peer {
            Some(a) => a.ip.is_loopback()
            None => false
        }
        sb.append(f" loopback={from_here}")
        return http.response(200, sb.build())
    }
    if path == "/trailers" {
        return http.response(200, "with trailers").with_trailer("X-Checksum", "42")
    }
    if path == "/big" {
        var n = 0
        for q in r.query() {
            if q.0 == "n" {
                n = int_of(q.1)
            }
        }
        var sb = StringBuilder()
        for i in 0..n {
            sb.append_byte(120)
        }
        return http.response(200, sb.build())
    }
    if path == "/bye" {
        return http.response(200, "bye").with_header("Connection", "close")
    }
    if path == "/bad-header" {
        return http.response(200, "x").with_header("X-Bad", "a\r\nInjected: 1")
    }
    return http.response(404, "no such page")
}

#main
async fun main() {
    let n = int_of(args()[1])
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("listen") }
    }
    match l.local_addr() {
        Ok(a) => println(f"{a.port}")
        Err(e) => panic("local_addr")
    }
    var o = http.server_options()
    o.max_requests = n
    o.max_header_bytes = 8192
    o.max_body_bytes = 1000000
    o.workers = 8
    match await http.serve_with(l, o, async (r: Request) => handle(r)) {
        Ok(k) => println(f"served {k}")
        Err(e) => println(f"server: {e}")
    }
    let c = l.close()
}
"""

# The requests the Python side makes that the server counts (the last one
# ends it).
SERVER_REQUESTS = 19


def recv_all(s: socket.socket) -> bytes:
    """What `s` receives until the peer closes."""
    out = b""
    while True:
        b = s.recv(65536)
        if not b:
            return out
        out += b


def recv_response(s: socket.socket) -> bytes:
    """One response with a Content-Length, read from `s`."""
    data = b""
    while b"\r\n\r\n" not in data:
        b = s.recv(65536)
        if not b:
            return data
        data += b
    head, _, rest = data.partition(b"\r\n\r\n")
    n = 0
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            n = int(value)
    while len(rest) < n:
        b = s.recv(65536)
        if not b:
            break
        rest += b
    return head + b"\r\n\r\n" + rest


def python_clients(test: unittest.TestCase, port: int) -> None:
    """Python's clients against the Myla server: SERVER_REQUESTS requests
    that reach the handler, and those its limits refuse."""
    def raw(data: bytes, wait_close: bool = True) -> bytes:
        with socket.create_connection(("127.0.0.1", port), timeout=30) as s:
            s.sendall(data)
            return recv_all(s) if wait_close else recv_response(s)

    # what the limits and the parser refuse, answered and closed (none of
    # them is counted)
    for request, status in [
        (b"BLAH\r\n\r\n", b"400 Bad Request"),
        (b"GET / HTTP/1.1\r\nBad Header\r\n\r\n", b"400 Bad Request"),
        (b"GET / HTTP/1.1\r\nHost: x\r\nX-Big: " + b"a" * 9000 + b"\r\n\r\n", b"431 Request Header Fields Too Large"),
        (b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 2000000\r\n\r\n", b"413 Content Too Large"),
        (b"POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: gzip\r\n\r\n", b"501 Not Implemented"),
        (b"GET / HTTP/2.0\r\n\r\n", b"505 HTTP Version Not Supported"),
        (b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 1x\r\n\r\n", b"400 Bad Request"),
        # H7 (MYLA-422): a chunk size that would take body_len + size past
        # int32 is 413, on every runner (it killed a checked server, and a
        # plain one waited for 2 GiB past its limit)
        (b"POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nx\r\n7fffffff\r\n", b"413 Content Too Large"),
        (b"POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n1 junk\r\nx\r\n0\r\n\r\n", b"400 Bad Request"),
        # two Host fields, a NUL and a bare CR in a value
        (b"GET / HTTP/1.1\r\nHost: x\r\nHost: y\r\n\r\n", b"400 Bad Request"),
        (b"GET / HTTP/1.1\r\nHost: x\r\nX-A: a\x00b\r\n\r\n", b"400 Bad Request"),
        (b"GET / HTTP/1.1\r\nHost: x\r\nX-A: a\rX-B: b\r\n\r\n", b"400 Bad Request"),
    ]:
        out = raw(request)
        test.assertTrue(out.startswith(b"HTTP/1.1 " + status + b"\r\n"), (request[:40], out))
        test.assertIn(b"Connection: close\r\n", out)

    # http.client: keep-alive on one connection (6 requests)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request("GET", "/hello")
    r = conn.getresponse()
    test.assertEqual((r.status, r.reason, r.read(), r.getheader("Content-Type")), (200, "OK", b"hello\n", "text/plain"))
    sock = conn.sock
    conn.request("POST", "/echo?a=1&b=x+y", body=b"data", headers={"X-One": "1", "x-two": "2"})
    r = conn.getresponse()
    test.assertEqual(r.read(), b"POST HTTP/1.1 body=data len=4 q[a=1] q[b=x y] h[X-One=1] h[x-two=2] loopback=true")
    conn.request("GET", "/trailers")
    r = conn.getresponse()
    test.assertEqual((r.getheader("Transfer-Encoding"), r.read()), ("chunked", b"with trailers"))
    conn.request("HEAD", "/hello")
    r = conn.getresponse()
    test.assertEqual((r.status, r.getheader("Content-Length"), r.read()), (200, "6", b""))
    conn.request("PUT", "/echo", body=iter([b"ab", b"cd"]), encode_chunked=True)
    r = conn.getresponse()
    test.assertEqual(r.read(), b"PUT HTTP/1.1 body=abcd len=4 loopback=true")
    conn.request("GET", "/big?n=200000")
    r = conn.getresponse()
    test.assertEqual(r.read(), b"x" * 200000)
    test.assertIs(conn.sock, sock, "one connection for all six")
    conn.close()

    # urllib (a connection of its own, closed after) and a 404 (2)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/hello", timeout=30) as u:
        test.assertEqual((u.status, u.read()), (200, b"hello\n"))
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/nowhere", timeout=30)
        test.fail("a 404 is an HTTPError")
    except urllib.error.HTTPError as e:
        test.assertEqual((e.code, e.read()), (404, b"no such page"))

    # Expect: 100-continue: the head, `100 Continue`, then the body (1)
    with socket.create_connection(("127.0.0.1", port), timeout=30) as s:
        s.sendall(b"POST /echo HTTP/1.1\r\nHost: x\r\nExpect: 100-continue\r\nContent-Length: 4\r\n\r\n")
        test.assertEqual(s.recv(100), b"HTTP/1.1 100 Continue\r\n\r\n")
        s.sendall(b"late")
        test.assertTrue(recv_response(s).endswith(b"\r\n\r\nPOST HTTP/1.1 body=late len=4 loopback=true"))

    # two requests pipelined in one write (2), bare LF line ends (1)
    out = raw(b"GET /hello HTTP/1.1\r\nHost: x\r\n\r\nGET /echo HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    test.assertEqual(out.count(b"HTTP/1.1 200 OK"), 2)
    test.assertTrue(out.endswith(b"GET HTTP/1.1 body= len=0 loopback=true"))
    test.assertIn(b"Connection: close\r\n", out)
    out = raw(b"GET /hello HTTP/1.1\nHost: x\nConnection: close\n\n")
    test.assertTrue(out.startswith(b"HTTP/1.1 200 OK\r\n") and out.endswith(b"\r\n\r\nhello\n"))

    # HTTP/1.0: closed after the answer, or kept with keep-alive (3)
    out = raw(b"GET /hello HTTP/1.0\r\n\r\n")
    test.assertTrue(out.startswith(b"HTTP/1.1 200 OK\r\n") and b"Connection: close\r\n" in out)
    with socket.create_connection(("127.0.0.1", port), timeout=30) as s:
        s.sendall(b"GET /hello HTTP/1.0\r\nConnection: keep-alive\r\n\r\n")
        first = recv_response(s)
        test.assertIn(b"Connection: keep-alive\r\n", first)
        s.sendall(b"GET /echo HTTP/1.0\r\n\r\n")
        test.assertTrue(recv_all(s).endswith(b"GET HTTP/1.0 body= len=0 loopback=true"))

    # a response that asks to close (1); one whose header can't be sent (1)
    out = raw(b"GET /bye HTTP/1.1\r\nHost: x\r\n\r\n")
    test.assertTrue(b"Connection: close\r\n" in out and out.endswith(b"bye"))
    out = raw(b"GET /bad-header HTTP/1.1\r\nHost: x\r\n\r\n")
    test.assertTrue(out.startswith(b"HTTP/1.1 500 Internal Server Error\r\n"), out)

    # a chunked upload with a trailer (1), and last a request without Host
    # (1), answered 400 and counted: the server ends after it
    out = raw(b"POST /echo HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
              b"3\r\nabc\r\n0\r\nX-Sum: 3\r\n\r\n")
    test.assertTrue(out.endswith(b"body=abc len=3 t[X-Sum=3] loopback=true"), out)
    out = raw(b"GET /hello HTTP/1.1\r\n\r\n")
    test.assertTrue(out.startswith(b"HTTP/1.1 400 Bad Request\r\n"), out)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipIf(NO_SOCKETS, NO_SOCKETS_WHY)
class MylaServer(unittest.TestCase):
    def test_answers_pythons_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, SERVER, "server.my")
            binary = os.path.join(tmp, "server")
            native_build(Program(path), binary)
            checked = os.path.join(tmp, "server-checked")
            native_build(Program(path), checked, checked=True)
            forms = {
                "interpreted": ([selfhost_tool("main"), "run", path, str(SERVER_REQUESTS), "--stdlib", STDLIB_ROOT],
                                None),
                "built": run_argv(binary, binary, [str(SERVER_REQUESTS)]),
                "built --checked": run_argv(checked, checked, [str(SERVER_REQUESTS)]),
            }
            for name, (argv, exe) in forms.items():
                with self.subTest(server=name):
                    proc = subprocess.Popen(argv, executable=exe, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            text=True)
                    try:
                        port = proc.stdout.readline().strip()
                        if not port.isdigit():
                            proc.kill()
                            self.fail(port + proc.stderr.read())
                        python_clients(self, int(port))
                        rest, err = proc.communicate(timeout=60)
                    finally:
                        proc.kill()
                    self.assertEqual((rest, err, proc.returncode), (f"served {SERVER_REQUESTS}\n", "", 0))


# --- how long the server keeps a connection ----------------------------------------

KEEP_SERVER = PRELUDE + r"""from std.io import println
import std.task as task

#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("listen") }
    }
    match l.local_addr() {
        Ok(a) => println(f"{a.port}")
        Err(e) => panic("local_addr")
    }
    var o = http.server_options()
    o.keep_alive_ms = int_of(args()[1])
    o.workers = 2
    let f = async () => await http.serve_with(l, o, async (r: Request) => http.response(200, "ok"))
    match await task.timeout(int_of(args()[2]), f) {
        Some(_) => println("ended")
        None => println("stopped")
    }
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipIf(NO_SOCKETS, NO_SOCKETS_WHY)
class KeepAlive(unittest.TestCase):
    def test_idle_and_busy_connections_are_closed_in_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, KEEP_SERVER, "keep.my")
            binary = os.path.join(tmp, "keep")
            native_build(Program(path), binary)
            args = ["400", "4000"]
            forms = {
                "interpreted": ([selfhost_tool("main"), "run", path, *args, "--stdlib", STDLIB_ROOT], None),
                "built": run_argv(binary, binary, args),
            }
            for name, (argv, exe) in forms.items():
                with self.subTest(server=name):
                    proc = subprocess.Popen(argv, executable=exe, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            text=True)
                    try:
                        port = int(proc.stdout.readline())
                        get = b"GET / HTTP/1.1\r\nHost: x\r\n\r\n"
                        # idle after one request: closed by the guard
                        with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
                            s.sendall(get)
                            first = recv_response(s)
                            t0 = time.monotonic()
                            self.assertNotIn(b"Connection: close", first)
                            self.assertEqual(s.recv(100), b"")
                            self.assertLess(time.monotonic() - t0, 3)
                        # busy: told to close with a response once the time
                        # is (nearly) up, then closed
                        with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
                            t0 = time.monotonic()
                            count = 0
                            while True:
                                s.sendall(get)
                                r = recv_response(s)
                                self.assertTrue(r.startswith(b"HTTP/1.1 200 OK\r\n"), r)
                                count += 1
                                if b"Connection: close\r\n" in r:
                                    break
                                time.sleep(0.02)
                            elapsed = time.monotonic() - t0
                            self.assertEqual(s.recv(100), b"")
                            self.assertGreater(count, 3)
                            self.assertTrue(0.25 < elapsed < 3, elapsed)
                        rest, err = proc.communicate(timeout=30)
                    finally:
                        proc.kill()
                    self.assertEqual((rest, err, proc.returncode), ("stopped\n", "", 0))


# --- the server's time limits (MYLA-422) -------------------------------------------

TIME_SERVER = PRELUDE + r"""from std.io import println
import std.task as task

fun handle(r: Request) -> Response {
    if r.path() == "/big" {
        // 8 MiB, doubled up
        var s = "x"
        while s.len() < 8388608 {
            s = s + s
        }
        return http.response(200, s)
    }
    if r.path() == "/echo" {
        return http.response(200, r.body)
    }
    return http.response(200, "ok")
}

async fun answer(r: Request) -> Response {
    if r.path() == "/sleep" {
        await task.sleep(700)
    }
    return handle(r)
}

fun time_of(s: str) -> int {
    return if s == "-" { -1 } else { int_of(s) }
}

// args: how long it runs, then `d` for the default options or the
// workers, keep_alive_ms, idle_ms, read_ms and write_ms (`-`: none)
#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("listen") }
    }
    match l.local_addr() {
        Ok(a) => println(f"{a.port}")
        Err(e) => panic("local_addr")
    }
    var o = http.server_options()
    let a = args()
    if a[2] != "d" {
        o.workers = int_of(a[2])
        o.keep_alive_ms = time_of(a[3])
        o.idle_ms = time_of(a[4])
        o.read_ms = time_of(a[5])
        o.write_ms = time_of(a[6])
    }
    let f = async () => await http.serve_with(l, o, async (r: Request) => await answer(r))
    match await task.timeout(int_of(a[1]), f) {
        Some(_) => println("ended")
        None => println("stopped")
    }
}
"""


def quick_get(port: int, timeout: float = 3) -> tuple[bytes, float]:
    """A GET on a connection of its own, closed after: the response and how
    long it took."""
    t0 = time.monotonic()
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        return recv_all(s), time.monotonic() - t0


def end_of(s: socket.socket, limit: float) -> tuple[bytes, float]:
    """What `s` receives until it ends (the end of the stream or a reset),
    and when, at most `limit` seconds from now."""
    t0 = time.monotonic()
    s.settimeout(limit)
    out = b""
    try:
        while True:
            b = s.recv(65536)
            if not b:
                break
            out += b
    except ConnectionResetError:
        pass
    return out, time.monotonic() - t0


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipIf(NO_SOCKETS, NO_SOCKETS_WHY)
class TimeLimits(unittest.TestCase):
    """The server's `idle_ms`, `read_ms`, `write_ms` and `keep_alive_ms`
    against Python's raw sockets: slow, silent and non-reading clients (the
    review's t_slow.py, M23)."""

    def forms(self, tmp: str, args: list[str]):
        path = os.path.join(tmp, "times.my")
        if not os.path.exists(path):
            write_program(tmp, TIME_SERVER, "times.my")
            native_build(Program(path), os.path.join(tmp, "times"))
        binary = os.path.join(tmp, "times")
        return {
            "interpreted": ([selfhost_tool("main"), "run", path, *args, "--stdlib", STDLIB_ROOT], None),
            "built": run_argv(binary, binary, args),
        }

    def serve(self, argv, exe, check):
        proc = subprocess.Popen(argv, executable=exe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            port = int(proc.stdout.readline())
            check(port)
            rest, err = proc.communicate(timeout=60)
        finally:
            proc.kill()
        self.assertEqual((rest, err, proc.returncode), ("stopped\n", "", 0))

    def test_idle_non_reading_and_slow_handled_connections(self):
        def check(port):
            # two silent connections hold both workers until idle_ms: then
            # they are closed without an answer, and a request is served
            idle = [socket.create_connection(("127.0.0.1", port), timeout=10) for _ in range(2)]
            time.sleep(0.1)
            out, took = quick_get(port, timeout=5)
            self.assertTrue(out.startswith(b"HTTP/1.1 200 OK\r\n"), out)
            self.assertLess(took, 2.5)
            for s in idle:
                self.assertEqual(end_of(s, 3)[0], b"")
                s.close()
            # two clients that never read an 8 MiB response hold both
            # workers until write_ms passes without progress
            hold = []
            for _ in range(2):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
                s.connect(("127.0.0.1", port))
                s.sendall(b"GET /big HTTP/1.1\r\nHost: x\r\n\r\n")
                hold.append(s)
            time.sleep(0.2)
            out, took = quick_get(port, timeout=8)
            self.assertTrue(out.startswith(b"HTTP/1.1 200 OK\r\n"), out)
            for s in hold:
                got, _ = end_of(s, 5)
                self.assertLess(len(got), 8 << 20, "closed before the whole response")
                s.close()
            # a handler slower than idle_ms and read_ms isn't cut, and its
            # connection is kept
            with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
                s.sendall(b"GET /sleep HTTP/1.1\r\nHost: x\r\n\r\n")
                first = recv_response(s)
                self.assertTrue(first.startswith(b"HTTP/1.1 200 OK\r\n") and first.endswith(b"\r\n\r\nok"), first)
                self.assertNotIn(b"Connection: close", first)
                s.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
                self.assertTrue(recv_response(s).endswith(b"\r\n\r\nok"))

        with tempfile.TemporaryDirectory() as tmp:
            for name, (argv, exe) in self.forms(tmp, ["12000", "2", "-", "300", "300", "300"]).items():
                with self.subTest(server=name):
                    self.serve(argv, exe, check)

    def test_slow_requests(self):
        def check(port):
            # an upload slower than keep_alive_ms, within read_ms: read
            # whole, answered, then the connection closes
            with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
                s.sendall(b"POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 12\r\n\r\n")
                for _ in range(12):
                    s.sendall(b"z")
                    time.sleep(0.1)
                out, _ = end_of(s, 5)
                self.assertTrue(out.startswith(b"HTTP/1.1 200 OK\r\n") and out.endswith(b"\r\n\r\n" + b"z" * 12), out)
                self.assertIn(b"Connection: close\r\n", out)
            # a head dribbled a byte at a time: 408 once read_ms passed
            with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
                t0 = time.monotonic()
                s.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nX-Slow: ")
                s.settimeout(0.1)
                out = b""
                while time.monotonic() - t0 < 6 and not out:
                    try:
                        s.sendall(b"a")
                        out = s.recv(65536)
                    except socket.timeout:
                        pass
                    except OSError:
                        break
                took = time.monotonic() - t0
                self.assertTrue(out.startswith(b"HTTP/1.1 408 Request Timeout\r\n"), out)
                self.assertTrue(1.0 < took < 4, took)

        with tempfile.TemporaryDirectory() as tmp:
            for name, (argv, exe) in self.forms(tmp, ["8000", "2", "400", "300", "1500", "500"]).items():
                with self.subTest(server=name):
                    self.serve(argv, exe, check)

    def test_silent_connections_renewed_do_not_stop_a_default_server(self):
        # the review's case (MYLA-422): 64 silent connections took every
        # worker of a default server for keep_alive_ms (60 s), then for
        # idle_ms (5 s); renewed every 4.5 s, they stopped it for good
        # (MYLA-468). A connection that has said nothing for a whole look of
        # its guard gives its worker up once another waits to be accepted.
        def check(port):
            stop = threading.Event()
            renewed = threading.Event()

            def renew():
                held = []
                while not stop.is_set():
                    fresh = [socket.create_connection(("127.0.0.1", port), timeout=10) for _ in range(64)]
                    for s in held:
                        s.close()
                    held = fresh
                    renewed.set()
                    stop.wait(4.5)
                for s in held:
                    s.close()

            attacker = threading.Thread(target=renew)
            attacker.start()
            try:
                took = []
                for _ in range(3):
                    # just after a renewal: every worker holds a fresh
                    # silent connection
                    renewed.wait()
                    renewed.clear()
                    time.sleep(0.2)
                    out, t = quick_get(port, timeout=15)
                    self.assertTrue(out.startswith(b"HTTP/1.1 200 OK\r\n"), out)
                    took.append(t)
                # two looks of a guard (a second each) at most, not the
                # 4.5 s until the next renewal
                self.assertLess(max(took), 3.2, took)
            finally:
                stop.set()
                attacker.join()

        with tempfile.TemporaryDirectory() as tmp:
            for name, (argv, exe) in self.forms(tmp, ["20000", "d"]).items():
                with self.subTest(server=name):
                    self.serve(argv, exe, check)


# --- what a client sends again on a new connection (MYLA-422) ---------------------

REPLAY_CLIENT = PRELUDE + r"""import std.task as task

#main
async fun main() {
    let base = f"http://127.0.0.1:{int_of(args()[1])}"
    var c = http.client()
    print(show(c.get(base + "/a")))
    // the server reads this POST and drops the kept connection without an
    // answer: it may have acted on it, so it isn't sent again
    print(show(c.post(base + "/swallow", "once")))
    print(show(c.get(base + "/a")))
    // a GET dropped so is sent again, once, on a new connection
    print(show(c.get(base + "/swallow-get")))
    // a kept connection the server closed before the POST: seen, and the
    // POST goes on a new one
    print(show(c.get(base + "/close-after")))
    await task.sleep(200)
    print(show(c.post(base + "/echo", "fresh")))
    c.close()
    var a = http.client()
    print(show(await a.get_async(base + "/a")))
    print(show(await a.post_async(base + "/swallow-async", "once")))
    print(show(await a.get_async(base + "/close-after")))
    await task.sleep(200)
    print(show(await a.post_async(base + "/echo", "fresh async")))
    a.close()
}
"""

REPLAY_OUT = """200 OK [a] Content-Length=1
error: connection closed
200 OK [a] Content-Length=1
200 OK [answered the second time] Content-Length=24
200 OK [closing] Content-Length=7
200 OK [POST fresh] Content-Length=10
200 OK [a] Content-Length=1
error: connection closed
200 OK [closing] Content-Length=7
200 OK [POST fresh async] Content-Length=16
"""


class ReplayServer:
    """A raw HTTP/1.1 server on 127.0.0.1 whose connections are kept, logging
    each request it reads: `/swallow…` paths are read and their connection
    closed without an answer (`/swallow-get` only the first time),
    `/close-after` is answered and its connection closed."""

    def __init__(self):
        self.log = []
        self.lock = threading.Lock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            try:
                s, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.serve, args=(s,), daemon=True).start()

    def serve(self, s: socket.socket):
        data = b""
        with s:
            while True:
                while b"\r\n\r\n" not in data:
                    b = s.recv(65536)
                    if not b:
                        return
                    data += b
                head, _, data = data.partition(b"\r\n\r\n")
                lines = head.decode().split("\r\n")
                method, path, _ = lines[0].split(" ")
                n = 0
                for line in lines[1:]:
                    name, _, value = line.partition(":")
                    if name.strip().lower() == "content-length":
                        n = int(value)
                while len(data) < n:
                    data += s.recv(65536)
                body, data = data[:n], data[n:]
                with self.lock:
                    self.log.append(f"{method} {path}")
                    seen = self.log.count(f"{method} {path}")
                if path.startswith("/swallow") and not (path == "/swallow-get" and seen > 1):
                    return
                text = {"/a": b"a", "/swallow-get": b"answered the second time", "/close-after": b"closing"}.get(
                    path, method.encode() + b" " + body)
                s.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (len(text), text))
                if path == "/close-after":
                    return

    def close(self):
        self.sock.close()


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipIf(NO_SOCKETS, NO_SOCKETS_WHY)
class NoReplay(unittest.TestCase):
    def test_only_idempotent_requests_are_sent_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, REPLAY_CLIENT, "replay.my")
            binary = os.path.join(tmp, "replay")
            native_build(Program(path), binary)
            for name in ["interpreted", "built"]:
                with self.subTest(client=name):
                    server = ReplayServer()
                    try:
                        if name == "interpreted":
                            out = selfhost_run(path, [str(server.port)])
                        else:
                            argv, exe = run_argv(binary, binary, [str(server.port)])
                            proc = subprocess.run(argv, executable=exe, capture_output=True, text=True, timeout=60)
                            out = (proc.stdout, proc.stderr, proc.returncode)
                    finally:
                        server.close()
                    self.assertEqual(out, (REPLAY_OUT, "", 0))
                    # each POST reached the server once; the dropped GET twice
                    self.assertEqual(server.log, [
                        "GET /a", "POST /swallow", "GET /a", "GET /swallow-get", "GET /swallow-get",
                        "GET /close-after", "POST /echo",
                        "GET /a", "POST /swallow-async", "GET /close-after", "POST /echo"])


# --- a Myla client and server in one program ---------------------------------------

ONE_PROGRAM = PRELUDE + r"""import std.task as task
import std.compress as compress
import std.bytes as bytes

fun handle(r: Request) -> Response {
    if r.path() == "/hello" {
        return http.response(200, f"hello {r.method} {r.body}").with_header("Content-Type", "text/plain")
    }
    if r.path() == "/redirect" {
        return http.response(302, "").with_header("Location", "/hello")
    }
    if r.path() == "/gzip" {
        let gz = compress_text("squeeze me, squeeze me, squeeze me")
        return http.response(200, gz).with_header("Content-Encoding", "gzip")
    }
    return http.response(404, "no such page")
}

fun compress_text(s: str) -> str {
    return bytes.to_str(compress.gzip(bytes.from_str(s)))
}

async fun client(port: int, name: str) -> str {
    let base = f"http://127.0.0.1:{port}"
    var c = http.client()
    var out = f"{name}:"
    for p in ["/hello", "/missing", "/redirect", "/gzip"] {
        match await c.get_async(base + p) {
            Ok(r) => { out = out + f" {r.status} [{r.text()}]" }
            Err(e) => { out = out + f" error {e}" }
        }
        await task.yield()
    }
    match await c.post_async(base + "/hello", name) {
        Ok(r) => { out = out + f" {r.status} [{r.text()}]" }
        Err(e) => { out = out + f" error {e}" }
    }
    c.close()
    return out
}

#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("listen") }
    }
    let port = match l.local_addr() {
        Ok(a) => a.port
        Err(e) => { panic("addr") }
    }
    async let served = http.serve_n(l, 18, handle)
    async let a = client(port, "a")
    async let b = client(port, "b")
    async let c = client(port, "c")
    print(await a)
    print(await b)
    print(await c)
    match await served {
        Ok(n) => print(f"served {n}")
        Err(e) => print(f"server: {e}")
    }
    // the listener is still open: a server of its own, stopped by a timeout
    let forever = async () => await http.serve_with(l, http.server_options(), async (r: Request) => handle(r))
    match await task.timeout(50, forever) {
        Some(r) => print("ended on its own")
        None => print("stopped by its timeout")
    }
    let closed = l.close()
}
"""
ONE_PROGRAM_OUT = "".join(
    f"{n}: 200 [hello GET ] 404 [no such page] 200 [hello GET ] 200 [squeeze me, squeeze me, squeeze me] 200 [hello POST {n}]\n"
    for n in "abc") + "served 18\nstopped by its timeout\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipIf(NO_SOCKETS, NO_SOCKETS_WHY)
class OneProgram(unittest.TestCase):
    def test_a_client_and_a_server_on_the_reactor(self):
        self.assertEqual(run_both(ONE_PROGRAM), (ONE_PROGRAM_OUT, "", 0))


# --- wasm32: no sockets ------------------------------------------------------------

ON_WASM = PRELUDE + r"""
#main
async fun main() {
    print(show(http.fetch("http://127.0.0.1:8080/")))
    print(show(await http.fetch_async("http://127.0.0.1:8080/")))
    match await http.serve(net.addr(net.loopback(), 0), (r: Request) => http.response(200, "")) {
        Ok(_) => print("served")
        Err(e) => print(f"serve: {e}")
    }
    // the pure parts work
    match http.parse_response("HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok") {
        Ok(r) => print(f"{r.status} {r.body}")
        Err(e) => print(f"{e}")
    }
}
"""
ON_WASM_OUT = "error: unsupported: sockets\nerror: unsupported: sockets\nserve: unsupported: sockets\n200 ok\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(NO_SOCKETS, "the wasm32 suite's (MYLA_TEST_TARGET=wasm32-wasi)")
class HttpOnWasm(unittest.TestCase):
    def test_every_exchange_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, ON_WASM)
            out = build_and_run_full(Program(path), argv0=path)
        self.assertEqual(out, (ON_WASM_OUT, "", 0))


if __name__ == "__main__":
    unittest.main()
