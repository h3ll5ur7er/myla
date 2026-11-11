"""Burn test: sockets, `std.net` and its primitives (MYLA-346).

- addresses: IPv4 and IPv6 parsed and printed (`::`, `[v6]:port`), as map keys;
- TCP: an echo between tasks of one program on the reactor (`accept_async`,
  `connect_async`, `read_async`, `write_async`), an accept that waits
  while another task runs, a listener in one program and a client in another
  (the blocking forms, through `std.io`'s `buffered`);
- UDP: datagrams sent and received, cut to the size asked, a receive that
  times out, one awaited while another task sends;
- names: a test hosts file, and DNS queries of a tiny fake name server this
  test runs on localhost UDP (no internet): A and AAAA records, a CNAME,
  "no such name", a server that fails, one that doesn't answer, a stray reply;
- errors: a refused connection, an address in use, one not this machine's,
  timeouts; on wasm32 (WASI has no sockets) every operation `Unsupported`.

Each program runs in the self-hosted interpreter and built for the test's
target, which must agree; `scripts/test-target.py` runs the suite for aarch64
(qemu: loopback networking works under qemu-user) and wasm32 (Node), where the
socket programs are excused (`_targets.py`) and `NetOnWasm` checks that each
operation is `Unsupported` instead. A program's call of a `__sock_*`
primitive is the primitive warning (D100, D161)."""
import os
import socket
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

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

PRELUDE = """from std.fs import IoError
import std.bytes as bytes
import std.net as net
from std.net import IpAddr, SocketAddr, TcpListener, TcpStream, UdpSocket

fun cause(e: IoError) -> str {
    return match e {
        IoError.ConnectionRefused => "ConnectionRefused"
        IoError.ConnectionReset => "ConnectionReset"
        IoError.AddrInUse => "AddrInUse"
        IoError.AddrNotAvailable => "AddrNotAvailable"
        IoError.TimedOut => "TimedOut"
        IoError.NotFound => "NotFound"
        IoError.Unsupported => "Unsupported"
        IoError.InvalidInput => "InvalidInput"
        IoError.InvalidData => "InvalidData"
        IoError.BrokenPipe => "BrokenPipe"
        IoError.Cancelled => "Cancelled"
        IoError.Other(code) => f"Other({code})"
        _ => "another error"
    }
}

fun listen_any() -> TcpListener {
    return match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => panic(f"listen: {cause(e)}")
    }
}

fun port_of(l: TcpListener) -> int {
    return match l.local_addr() {
        Ok(a) => a.port
        Err(e) => panic(f"local_addr: {cause(e)}")
    }
}

fun ips(r: Result<[IpAddr], IoError>) -> str {
    return match r {
        Ok(xs) => {
            var sb = StringBuilder()
            for ip in xs {
                if sb.len() > 0 {
                    sb.append(" ")
                }
                sb.append(f"{ip}")
            }
            sb.build()
        }
        Err(e) => cause(e)
    }
}

fun int_of(s: str) -> int {
    var v = 0
    for c in s {
        v = v * 10 + (c - '0')
    }
    return v
}

"""

ADDRESSES = PRELUDE + """fun show_ip(s: str) -> str {
    return match net.parse_ip(s) {
        Ok(ip) => f"{ip}"
        Err(e) => f"error: {e}"
    }
}

fun show_addr(s: str) -> str {
    return match net.parse_addr(s) {
        Ok(a) => f"{a} port {a.port}"
        Err(e) => f"error: {e}"
    }
}

fun main() {
    for s in ["127.0.0.1", "10.0.0.255", "::", "::1", "2001:db8:0:0:1:0:0:1", "2001:DB8::8:800:200C:417A",
              "fe80::", "::ffff:192.0.2.128", "1:2:3:4:5:6:7:8", "1.2.3.256", "1:2:3:4:5:6:7:8:9", "1::2::3", ""] {
        print(show_ip(s))
    }
    for s in ["127.0.0.1:8080", "[::1]:443", "[2001:db8::1]:0", "[::1]", "::1:80", "1.2.3.4:99999", "1.2.3.4"] {
        print(show_addr(s))
    }
    let a = match net.parse_addr("[::1]:80") {
        Ok(a) => a
        Err(e) => panic("parse")
    }
    print(a == net.addr(net.loopback_v6(), 80))
    print(a == net.addr(net.loopback(), 80))
    var seen: [SocketAddr: str] = [:]
    seen[a] = "v6"
    seen[net.addr(net.loopback(), 80)] = "v4"
    seen[net.addr(IpAddr.V6(0, 0, 0, 0, 0, 0, 0, 1), 80)] = "v6 again"
    print(seen.len())
    print(seen[a])
    print(f"{net.loopback().is_loopback()} {net.loopback_v6().is_ipv6()} {net.unspecified().is_unspecified()}")
    print(net.loopback_v6().octets().len())
    print(f"[{net.addr(net.loopback(), 7):>16}]")
}
"""
ADDRESSES_OUT = """127.0.0.1
10.0.0.255
::
::1
2001:db8::1:0:0:1
2001:db8::8:800:200c:417a
fe80::
::ffff:192.0.2.128
1:2:3:4:5:6:7:8
error: invalid IP address
error: invalid IP address
error: invalid IP address
error: empty address
127.0.0.1:8080 port 8080
[::1]:443 port 443
[2001:db8::1]:0 port 0
error: missing port
error: missing port
error: invalid port
error: missing port
true
false
2
v6 again
true true true
16
[     127.0.0.1:7]
"""

# Two clients at once and a server serving them in turn, every wait on the
# reactor; then an accept that waits while a sleeping task runs, and a read
# a timeout stops.
ECHO = PRELUDE + """import std.task as task

async fun serve(l: TcpListener, n: int) -> int {
    var total = 0
    var k = 0
    while k < n {
        var s = match await l.accept_async() {
            Ok(s) => s
            Err(e) => { return -1 }
        }
        while true {
            let chunk = match await s.read_async(4096) {
                Ok(c) => c
                Err(e) => { return -2 }
            }
            if chunk.len() == 0 {
                break
            }
            total += chunk.len()
            match await s.write_async(chunk) {
                Ok(_) => {}
                Err(e) => { return -3 }
            }
        }
        let c = s.close()
        k += 1
    }
    return total
}

async fun client(port: int, words: [str]) -> str {
    var s = match await net.connect_async(net.addr(net.loopback(), port)) {
        Ok(s) => s
        Err(e) => { return f"connect: {cause(e)}" }
    }
    var got = ""
    for word in words {
        let w = await s.write_async(bytes.from_str(word))
        var want = word.len()
        while want > 0 {
            match await s.read_async(100) {
                Ok(t) => {
                    got = got + bytes.to_str(t)
                    want -= t.len()
                }
                Err(e) => { return f"read: {cause(e)}" }
            }
        }
    }
    let sh = s.shutdown(net.Shutdown.Write)
    let rest = await s.read_async(100)
    let c = s.close()
    return match rest {
        Ok(r) => f"{got} (then {r.len()} bytes)"
        Err(e) => cause(e)
    }
}

async fun accept_one(l: TcpListener) -> str {
    return match await l.accept_async() {
        Ok(s) => {
            var t = s
            let peer = match t.peer_addr() {
                Ok(a) => a.ip.is_loopback()
                Err(e) => false
            }
            let c = t.close()
            f"accepted, from this machine: {peer}"
        }
        Err(e) => cause(e)
    }
}

async fun late(port: int) -> str {
    await task.sleep(30)
    print("the other task ran")
    return match net.connect(net.addr(net.loopback(), port)) {
        Ok(s) => {
            var t = s
            let c = t.close()
            "connected"
        }
        Err(e) => cause(e)
    }
}

async fun silent_read(port: int) -> str {
    var s = match net.connect(net.addr(net.loopback(), port)) {
        Ok(s) => s
        Err(e) => { return cause(e) }
    }
    let r = await s.read_async(10)
    let c = s.close()
    return match r {
        Ok(t) => f"read {t.len()} bytes"
        Err(e) => cause(e)
    }
}

#main
async fun main() {
    var l = listen_any()
    let port = port_of(l)
    async let server = serve(l, 2)
    async let a = client(port, ["hello", " ", "world"])
    async let b = client(port, ["one", "two", "three"])
    print(await a)
    print(await b)
    print(await server)

    async let acc = accept_one(l)
    async let other = late(port)
    print(await other)
    print(await acc)

    // nothing comes: the timeout stops the waiting read
    let f = async () => await silent_read(port)
    match await task.timeout(50, f) {
        Some(r) => print(r)
        None => print("timed out")
    }
    let c = l.close()
}
"""
ECHO_OUT = """hello world (then 0 bytes)
onetwothree (then 0 bytes)
22
the other task ran
connected
accepted, from this machine: true
timed out
"""

# One task and no other: the program has no reactor, and an async form's
# wait blocks the thread in `__sock_poll` (the lowering of `__wait_socket`
# without tasks, and the interpreter's outside any task).
ONE_TASK = """import std.net as net
import std.bytes as bytes

#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("listen") }
    }
    let at = match l.local_addr() {
        Ok(a) => a
        Err(e) => { panic("addr") }
    }
    var c = match await net.connect_async(at) {
        Ok(s) => s
        Err(e) => { panic("connect") }
    }
    var s = match await l.accept_async() {
        Ok(s) => s
        Err(e) => { panic("accept") }
    }
    let w = await c.write_async(bytes.from_str("one task"))
    match await s.read_async(100) {
        Ok(t) => print(bytes.to_str(t))
        Err(e) => print("read failed")
    }
    let x = c.close()
    let y = s.close()
    let z = l.close()
}
"""

# A listener in one program, the client in another: the blocking forms, each
# stream through `std.io`'s `buffered`.
SERVER = PRELUDE + """from std.io import buffered, println

fun upper(s: str) -> str {
    var sb = StringBuilder()
    for c in s {
        if c >= 'a' && c <= 'z' {
            sb.append_byte((c - 32 as int32) as uint8)
        } else {
            sb.append(f"{c}")
        }
    }
    return sb.build()
}

fun main() {
    var l = listen_any()
    println(f"{port_of(l)}")
    var s = match l.accept() {
        Ok(s) => s
        Err(e) => panic(f"accept: {cause(e)}")
    }
    var out = s
    var lines = buffered(s)
    var n = 0
    while true {
        match lines.read_line() {
            Ok(Some(line)) => {
                if line == "quit" {
                    break
                }
                n += 1
                match out.write(bytes.from_str(upper(line) + "\\n")) {
                    Ok(_) => {}
                    Err(e) => panic(f"write: {cause(e)}")
                }
            }
            Ok(None) => { break }
            Err(e) => panic(f"read: {cause(e)}")
        }
    }
    println(f"served {n} lines")
    match out.peer_addr() {
        Ok(a) => println(f"from {a.ip}")
        Err(e) => println(cause(e))
    }
    let c = out.close()
    let d = l.close()
}
"""

CLIENT = PRELUDE + """from std.io import buffered
from std.process import args

fun main() {
    let port = int_of(args()[1])
    var s = match net.connect(net.addr(net.loopback(), port)) {
        Ok(s) => s
        Err(e) => panic(f"connect: {cause(e)}")
    }
    var out = s
    var lines = buffered(s)
    for line in ["abc", "Hello, World", "a longer line, with more in it"] {
        let w = out.write(bytes.from_str(line + "\\n"))
        match lines.read_line() {
            Ok(Some(back)) => print(back)
            Ok(None) => print("the end")
            Err(e) => print(cause(e))
        }
    }
    let q = out.write(bytes.from_str("quit\\n"))
    // the server closes: the end of the stream
    match lines.read_line() {
        Ok(None) => print("the end")
        Ok(Some(more)) => print(more)
        Err(e) => print(cause(e))
    }
    let c = out.close()
}
"""
CLIENT_OUT = "ABC\nHELLO, WORLD\nA LONGER LINE, WITH MORE IN IT\nthe end\n"

UDP = PRELUDE + """import std.task as task

fun bound(ip: IpAddr) -> Result<UdpSocket, IoError> {
    return net.udp_bind(net.addr(ip, 0))
}

fun local(u: UdpSocket) -> SocketAddr {
    return match u.local_addr() {
        Ok(a) => a
        Err(e) => panic(cause(e))
    }
}

async fun send_later(to: SocketAddr) -> str {
    await task.sleep(20)
    var u = match bound(net.loopback()) {
        Ok(u) => u
        Err(e) => { return cause(e) }
    }
    let r = u.send_str_to("later", to)
    let c = u.close()
    return "sent"
}

// The same over IPv6's loopback, when the machine has one.
fun over_v6() -> str {
    var a = match bound(net.loopback_v6()) {
        Ok(u) => u
        Err(e) => { return "v6: unavailable" }
    }
    var b = match bound(net.loopback_v6()) {
        Ok(u) => u
        Err(e) => { return "v6: unavailable" }
    }
    let sent = b.send_str_to("six", local(a))
    let r = match a.recv_str_from(100) {
        Ok((msg, src)) => f"v6: {msg} from {src.ip} {src == local(b)}"
        Err(e) => f"v6: {cause(e)}"
    }
    let c = a.close()
    let d = b.close()
    return r
}

#main
async fun main() {
    var a = match bound(net.loopback()) {
        Ok(u) => u
        Err(e) => panic(cause(e))
    }
    var b = match bound(net.loopback()) {
        Ok(u) => u
        Err(e) => panic(cause(e))
    }
    match b.send_str_to("ping", local(a)) {
        Ok(n) => print(n)
        Err(e) => print(cause(e))
    }
    match a.recv_str_from(100) {
        Ok((msg, src)) => {
            print(msg)
            print(src == local(b))
            let back = a.send_to([1u8, 2u8, 3u8], src)
        }
        Err(e) => print(cause(e))
    }
    // a datagram longer than asked: the rest is dropped
    match b.recv_from(2) {
        Ok((bytes, src)) => print(f"{bytes.len()} {bytes[0]} {bytes[1]} {src == local(a)}")
        Err(e) => print(cause(e))
    }
    a.set_read_timeout(30)
    match a.recv_str_from(10) {
        Ok((msg, src)) => print(msg)
        Err(e) => print(cause(e))
    }
    // awaited while another task sends
    async let s = send_later(local(a))
    match await a.recv_str_from_async(100) {
        Ok((msg, src)) => print(msg)
        Err(e) => print(cause(e))
    }
    print(await s)
    let c = a.close()
    let d = b.close()
    print(over_v6())
}
"""
UDP_OUT = "4\nping\ntrue\n2 1 2 true\nTimedOut\nlater\nsent\n"

HOSTS = PRELUDE + """from std.process import args

fun main() {
    let r = net.resolver(args()[1], [])
    print(ips(r.lookup("db.test")))
    print(ips(r.lookup("DB.Test.")))
    print(ips(r.lookup("alias.test")))
    print(ips(r.lookup("v6.test")))
    print(ips(r.lookup("nothere.test")))
    print(ips(r.lookup("192.0.2.7")))
    print(ips(r.lookup("::1")))
    print(ips(r.lookup("a..b")))
    print(ips(net.resolver(args()[1] + ".missing", []).lookup("db.test")))
    // localhost: the hosts file's entries, else the loopback (MYLA-426)
    print(ips(r.lookup("localhost")))
    print(ips(net.resolver(args()[1] + ".missing", []).lookup("Localhost.")))
    print(ips(net.resolver("", []).lookup("db.localhost")))
}
"""
HOSTS_FILE = ("# a test hosts file\r\n"
              "127.0.0.1\tlocalhost\r\n"
              "10.1.2.3   db.test alias.test   # the database\r\n"
              "2001:db8::3 db.test\r\n"
              "fe80::1 v6.test\n"
              "not-an-address bogus.test\n")
HOSTS_OUT = """10.1.2.3 2001:db8::3
10.1.2.3 2001:db8::3
10.1.2.3
fe80::1
NotFound
192.0.2.7
::1
InvalidInput
NotFound
127.0.0.1
127.0.0.1 ::1
127.0.0.1 ::1
"""

DNS = PRELUDE + """from std.process import args

fun main() {
    var r = net.resolver("", [net.addr(net.loopback(), int_of(args()[1]))])
    r.timeout_ms = 300
    r.attempts = 1
    for name in ["www.example.test", "v4only.example.test", "alias.example.test", "WWW.Example.Test.",
                 "noisy.example.test", "nx.example.test", "broken.example.test", "silent.example.test"] {
        print(f"{name}: {ips(r.lookup(name))}")
    }
}
"""
DNS_OUT = """www.example.test: 192.0.2.10 192.0.2.11 2001:db8::10
v4only.example.test: 192.0.2.20
alias.example.test: 192.0.2.10 192.0.2.11 2001:db8::10
WWW.Example.Test.: 192.0.2.10 192.0.2.11 2001:db8::10
noisy.example.test: 192.0.2.30
nx.example.test: NotFound
broken.example.test: InvalidData
silent.example.test: TimedOut
"""

ERRORS = PRELUDE + """fun main() {
    // nobody listens there any more
    var gone = listen_any()
    let port = port_of(gone)
    let c = gone.close()
    match net.connect(net.addr(net.loopback(), port)) {
        Ok(s) => print("connected")
        Err(e) => print(cause(e))
    }
    match net.connect_timeout(net.addr(net.loopback(), port), 1000) {
        Ok(s) => print("connected")
        Err(e) => print(cause(e))
    }
    // the port is taken
    var l = listen_any()
    let taken = net.addr(net.loopback(), port_of(l))
    match net.listen(taken) {
        Ok(other) => print("listening twice")
        Err(e) => print(cause(e))
    }
    var u = match net.udp_bind(net.addr(net.loopback(), 0)) {
        Ok(u) => u
        Err(e) => panic(cause(e))
    }
    let uport = match u.local_addr() {
        Ok(a) => a.port
        Err(e) => 0
    }
    match net.udp_bind(net.addr(net.loopback(), uport)) {
        Ok(other) => print("bound twice")
        Err(e) => print(cause(e))
    }
    // not an address of this machine (TEST-NET-1)
    match net.listen(net.addr(IpAddr.V4(192, 0, 2, 1), 0)) {
        Ok(other) => print("listening there")
        Err(e) => print(cause(e))
    }
    // waits that time out
    l.set_timeout(30)
    match l.accept() {
        Ok(s) => print("accepted")
        Err(e) => print(cause(e))
    }
    var s = match net.connect(taken) {
        Ok(s) => s
        Err(e) => panic(cause(e))
    }
    s.set_read_timeout(30)
    match s.read(10) {
        Ok(t) => print(f"read {t.len()} bytes")
        Err(e) => print(cause(e))
    }
    // the peer closes: the end of the stream, then a closed stream
    var peer = match l.accept() {
        Ok(p) => p
        Err(e) => panic(cause(e))
    }
    let pc = peer.close()
    match s.read(10) {
        Ok(t) => print(f"read {t.len()} bytes")
        Err(e) => print(cause(e))
    }
    let sc = s.close()
    let again = s.close()
    print(match again {
        Ok(()) => "closed twice"
        Err(e) => cause(e)
    })
    match s.read(10) {
        Ok(t) => print(f"read {t.len()} bytes")
        Err(e) => print(cause(e))
    }
    let uc = u.close()
    let lc = l.close()
}
"""
ERRORS_OUT = """ConnectionRefused
ConnectionRefused
AddrInUse
AddrInUse
AddrNotAvailable
TimedOut
TimedOut
read 0 bytes
closed twice
Other(9)
"""

# D181 (the 2026-11-09 review's M13): a copy of a closed stream, listener or
# UDP socket, and one built by hand, reach nothing; before, the copy wrote
# into and closed whichever socket got the descriptor next
STALE = PRELUDE + """fun said(r: Result<int, IoError>) -> str {
    return match r {
        Ok(n) => f"Ok({n})"
        Err(e) => cause(e)
    }
}

fun closed(r: Result<(), IoError>) -> str {
    return match r {
        Ok(()) => "Ok"
        Err(e) => cause(e)
    }
}

fun accept_one(l: TcpListener) -> TcpStream {
    return match l.accept() {
        Ok(s) => s
        Err(e) => panic(f"accept: {cause(e)}")
    }
}

fun main() {
    var l = listen_any()
    let at = net.addr(net.loopback(), port_of(l))
    var a = match net.connect(at) {
        Ok(s) => s
        Err(e) => panic(cause(e))
    }
    var a_srv = accept_one(l)
    var stale = a
    let c = a.close()
    // a second connection, which may get the closed one's descriptor
    var b = match net.connect(at) {
        Ok(s) => s
        Err(e) => panic(cause(e))
    }
    var b_srv = accept_one(l)
    print(f"stale write: {said(stale.write(bytes.from_str("INJECTED")))}")
    b_srv.set_read_timeout(100)
    match b_srv.read(100) {
        Ok(t) => print(f"b's server end read '{bytes.to_str(t)}'")
        Err(e) => print(f"b's server end read: {cause(e)}")
    }
    print(f"stale close: {closed(stale.close())}")
    print(f"b write: {said(b.write(bytes.from_str("hello")))}")
    match b_srv.read(100) {
        Ok(t) => print(f"b's server end read '{bytes.to_str(t)}'")
        Err(e) => print(f"b's server end read: {cause(e)}")
    }
    // a stream, a listener and a UDP socket built by hand
    var forged = TcpStream { handle: 4, read_ms: -1, write_ms: -1 }
    print(f"forged write: {said(forged.write(bytes.from_str("x")))}")
    var forged_l = TcpListener { handle: 3, timeout_ms: 10 }
    match forged_l.accept() {
        Ok(s) => print("accepted")
        Err(e) => print(f"forged accept: {cause(e)}")
    }
    var u = match net.udp_bind(net.addr(net.loopback(), 0)) {
        Ok(u) => u
        Err(e) => panic(cause(e))
    }
    var u_copy = u
    let uc = u.close()
    print(f"stale send: {said(u_copy.send_to(bytes.from_str("x"), at))}")
    // a stale listener: it accepts nothing more
    var l_copy = l
    let lc = l.close()
    match l_copy.accept() {
        Ok(s) => print("accepted")
        Err(e) => print(f"stale accept: {cause(e)}")
    }
    let x = a_srv.close()
    let y = b.close()
    let z = b_srv.close()
}
"""
STALE_OUT = """stale write: Other(9)
b's server end read: TimedOut
stale close: Other(9)
b write: Ok(5)
b's server end read 'hello'
forged write: Other(9)
forged accept: Other(9)
stale send: Other(9)
stale accept: Other(9)
"""

# D180: lines of text over sockets in tasks, without blocking a worker
# (`net.line_reader`): 20 connections echo lines given in pieces, with a
# "\r" kept and a last line without "\n", also on one worker, where
# `io.buffered(s).read_line()` hangs
LINES = """import std.net as net
import std.task as task
import std.bytes as bytes
from std.net import TcpStream, TcpListener, SocketAddr

async fun serve_one(s: TcpStream) -> int {
    var out = s
    var r = net.line_reader(s)
    var n = 0
    while true {
        match await r.read_line_async() {
            Ok(Some(line)) => {
                n += 1
                let w = await out.write_async(bytes.from_str(line + "\\n"))
            }
            _ => { break }
        }
    }
    let c = out.close()
    return n
}

async fun serve(l: TcpListener, conns: int) -> int {
    var jobs: [async () -> int] = []
    for k in 0..conns {
        match await l.accept_async() {
            Ok(s) => { jobs.push(async () => await serve_one(s)) }
            Err(e) => { return -1 }
        }
    }
    var total = 0
    for n in await task.all(jobs) { total += n }
    return total
}

async fun client(at: SocketAddr, id: int, count: int) -> int {
    var s = match await net.connect_async(at) {
        Ok(s) => s
        Err(e) => { return -1 }
    }
    var r = net.line_reader(s)
    var ok = 0
    for i in 0..count {
        let msg = f"client {id} line {i} grüße €"
        // a line in two pieces, the second with the next line's start
        let w = await s.write_async(bytes.from_str(msg + "\\r"))
        let w2 = await s.write_async(bytes.from_str("\\n"))
        match await r.read_line_async() {
            Ok(Some(back)) => { if back == msg + "\\r" { ok += 1 } }
            _ => { break }
        }
    }
    // a last line without "\\n", then the end
    let w = await s.write_async(bytes.from_str("tail"))
    let sh = s.shutdown(net.Shutdown.Write)
    match await r.read_line_async() {
        Ok(Some(back)) => { if back == "tail" { ok += 1 } }
        _ => {}
    }
    match await r.read_line_async() {
        Ok(None) => { ok += 1 }
        _ => {}
    }
    let c = s.close()
    return ok
}

#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) { Ok(l) => l, Err(e) => { panic("listen") } }
    let at = match l.local_addr() { Ok(a) => a, Err(e) => { panic("addr") } }
    let conns = 20
    async let served = serve(l, conns)
    var cs: [async () -> int] = []
    for id in 0..conns {
        cs.push(async () => await client(at, id, 50))
    }
    var total = 0
    for n in await task.all(cs) { total += n }
    print(f"clients ok {total}")
    print(f"server lines {await served}")
    let d = l.close()
}
"""
LINES_OUT = "clients ok 1040\nserver lines 1020\n"

NET_WASM = PRELUDE + """fun main() {
    match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => print("listening")
        Err(e) => print(cause(e))
    }
    match net.connect(net.addr(net.loopback(), 80)) {
        Ok(s) => print("connected")
        Err(e) => print(cause(e))
    }
    match net.udp_bind(net.addr(net.loopback(), 0)) {
        Ok(u) => print("bound")
        Err(e) => print(cause(e))
    }
    print(ips(net.resolver("", [net.addr(net.loopback(), 53)]).lookup("www.example.test")))
    print(ips(net.lookup("www.example.test")))
    print(ips(net.lookup("127.0.0.1")))
    // no hosts file, but localhost is the loopback (RFC 6761, MYLA-426)
    print(ips(net.lookup("localhost")))
    print(ips(net.lookup("db.LOCALHOST.")))
}
"""
NET_WASM_OUT = "Unsupported\nUnsupported\nUnsupported\nUnsupported\nNotFound\n127.0.0.1\n127.0.0.1 ::1\n127.0.0.1 ::1\n"


def run_both(source: str, args=()) -> tuple[str, str, int]:
    """`source` in the self-hosted interpreter and built for the test's
    target, which must agree; their (stdout, stderr, exit)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = write_program(tmp, source)
        interp = selfhost_run(path, list(args))
        native = build_and_run_full(Program(path), args=list(args), argv0=path)
    assert interp == native, f"interpreter {interp!r} != native {native!r}"
    return interp


def has_ipv6_loopback() -> bool:
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as s:
            s.bind(("::1", 0))
        return True
    except OSError:
        return False


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Addresses(unittest.TestCase):
    def test_parsed_printed_compared_and_hashed(self):
        self.assertEqual(run_both(ADDRESSES), (ADDRESSES_OUT, "", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Tcp(unittest.TestCase):
    def test_an_echo_between_tasks_on_the_reactor(self):
        self.assertEqual(run_both(ECHO), (ECHO_OUT, "", 0))

    def test_the_async_forms_in_a_program_of_one_task(self):
        self.assertEqual(run_both(ONE_TASK), ("one task\n", "", 0))

    def test_lines_in_tasks_on_any_number_of_workers(self):
        self.assertEqual(run_both(LINES), (LINES_OUT, "", 0))
        with mock.patch.dict(os.environ, {"MYLA_THREADS": "1"}):
            self.assertEqual(run_both(LINES), (LINES_OUT, "", 0))

    def test_a_closed_or_made_up_handle_reaches_nothing(self):
        self.assertEqual(run_both(STALE), (STALE_OUT, "", 0))

    def test_a_listener_and_a_client_in_two_programs(self):
        # each side interpreted and built, against the other's two forms
        with tempfile.TemporaryDirectory() as tmp:
            server = write_program(tmp, SERVER, "server.my")
            client = write_program(tmp, CLIENT, "client.my")
            sbin = os.path.join(tmp, "server")
            cbin = os.path.join(tmp, "client")
            native_build(Program(server), sbin)
            native_build(Program(client), cbin)
            interp = [selfhost_tool("main"), "run"]
            servers = {"interpreted": ([*interp, server, "--stdlib", STDLIB_ROOT], None),
                       "built": run_argv(sbin, sbin)}
            for sname, (sargv, sexe) in servers.items():
                for cname in ("interpreted", "built"):
                    with self.subTest(server=sname, client=cname):
                        proc = subprocess.Popen(sargv, executable=sexe, stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE, text=True)
                        try:
                            port = proc.stdout.readline().strip()
                            if not port.isdigit():
                                proc.kill()
                                self.fail(port + proc.stderr.read())
                            if cname == "interpreted":
                                out = subprocess.run([*interp, client, port, "--stdlib", STDLIB_ROOT],
                                                     capture_output=True, text=True, timeout=60)
                            else:
                                cargv, cexe = run_argv(cbin, cbin, [port])
                                out = subprocess.run(cargv, executable=cexe, capture_output=True, text=True,
                                                     timeout=60)
                            rest, err = proc.communicate(timeout=60)
                        finally:
                            proc.kill()
                        self.assertEqual((out.stdout, out.stderr, out.returncode), (CLIENT_OUT, "", 0))
                        self.assertEqual((rest, err, proc.returncode), ("served 3 lines\nfrom 127.0.0.1\n", "", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Udp(unittest.TestCase):
    def test_datagrams_sent_received_cut_and_awaited(self):
        out, err, code = run_both(UDP)
        if has_ipv6_loopback():
            v6 = "v6: six from ::1 true\n"
        else:
            v6 = "v6: unavailable\n"
        self.assertEqual((out, err, code), (UDP_OUT + v6, "", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Hosts(unittest.TestCase):
    def test_a_hosts_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hosts")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(HOSTS_FILE)
            self.assertEqual(run_both(HOSTS, [path]), (HOSTS_OUT, "", 0))


class FakeDns:
    """A name server on 127.0.0.1 UDP for the names of DNS: A and AAAA records
    (`www`), only A (`v4only`), a CNAME to `www` (`alias`), a stray reply with
    another id before the real one (`noisy`), NXDOMAIN (`nx`), SERVFAIL
    (`broken`), no answer at all (`silent`). It records the queries."""

    A = {"www.example.test": ["192.0.2.10", "192.0.2.11"], "v4only.example.test": ["192.0.2.20"],
         "noisy.example.test": ["192.0.2.30"]}
    AAAA = {"www.example.test": ["2001:db8::10"]}

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.queries: list[tuple[str, int]] = []
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def close(self):
        self.sock.close()

    @staticmethod
    def name_at(msg: bytes, at: int) -> tuple[str, int]:
        labels = []
        while msg[at] != 0:
            n = msg[at]
            labels.append(msg[at + 1:at + 1 + n].decode())
            at += 1 + n
        return ".".join(labels), at + 1

    def serve(self):
        while True:
            try:
                msg, peer = self.sock.recvfrom(512)
            except OSError:
                return
            qid, flags, qd = struct.unpack(">HHH", msg[:6])
            name, end = self.name_at(msg, 12)
            qtype, qclass = struct.unpack(">HH", msg[end:end + 4])
            question = msg[12:end + 4]
            key = name.lower()
            self.queries.append((key, qtype))
            if key.startswith("silent."):
                continue
            rcode = 0
            answers = b""
            count = 0
            if key.startswith("nx."):
                rcode = 3
            elif key.startswith("broken."):
                rcode = 2
            else:
                target = key
                if key == "alias.example.test":
                    # the CNAME's data: "www" and a pointer to "example.test"
                    # in the question (offset 12 + len("alias") + 1)
                    rdata = b"\x03www" + struct.pack(">H", 0xC000 | (12 + 6))
                    answers += struct.pack(">HHHIH", 0xC00C, 5, 1, 60, len(rdata)) + rdata
                    count += 1
                    target = "www.example.test"
                table = self.A if qtype == 1 else self.AAAA
                fam = socket.AF_INET if qtype == 1 else socket.AF_INET6
                for ip in table.get(target, []):
                    raw = socket.inet_pton(fam, ip)
                    answers += struct.pack(">HHHIH", 0xC00C, qtype, 1, 60, len(raw)) + raw
                    count += 1
            header = struct.pack(">HHHHHH", qid, 0x8180 | rcode, 1, count, 0, 0)
            if key.startswith("noisy."):
                self.sock.sendto(struct.pack(">HHHHHH", qid ^ 1, 0x8180, 1, 0, 0, 0) + question, peer)
            self.sock.sendto(header + question + answers, peer)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Dns(unittest.TestCase):
    def test_queries_of_a_fake_name_server(self):
        dns = FakeDns()
        try:
            self.assertEqual(run_both(DNS, [str(dns.port)]), (DNS_OUT, "", 0))
        finally:
            dns.close()
        # an A query then an AAAA one for each name (a "no such name" ends at
        # the first; the server that doesn't answer is asked once)
        self.assertIn(("www.example.test", 1), dns.queries)
        self.assertIn(("www.example.test", 28), dns.queries)
        self.assertEqual(dns.queries.count(("nx.example.test", 1)), 2)
        self.assertNotIn(("nx.example.test", 28), dns.queries)
        self.assertEqual(dns.queries.count(("silent.example.test", 1)), 2)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Errors(unittest.TestCase):
    def test_refused_in_use_not_here_timeouts(self):
        self.assertEqual(run_both(ERRORS), (ERRORS_OUT, "", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(TEST_TARGET == "wasm32-wasi", "the wasm32 suite's (scripts/test-target.py wasm32-wasi)")
class NetOnWasm(unittest.TestCase):
    def test_every_operation_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, NET_WASM)
            out = build_and_run_full(Program(path), argv0=path)
        self.assertEqual(out, (NET_WASM_OUT, "", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Warnings(unittest.TestCase):
    """Outside `std` each primitive is the primitive warning (D100), which
    `#allow` silences (D161), as every I/O primitive's is."""

    CALLS = {
        "__sock_open": "print(__sock_open(4, 1))",
        "__sock_set_nonblocking": "print(__sock_set_nonblocking(-1, 1))",
        "__sock_bind": "print(__sock_bind(-1, \"\"))",
        "__sock_listen": "print(__sock_listen(-1, 1))",
        "__sock_accept": "print(__sock_accept(-1))",
        "__sock_connect": "print(__sock_connect(-1, \"\"))",
        "__sock_error": "print(__sock_error(-1))",
        "__sock_send": "print(__sock_send(-1, \"x\", 0))",
        "__sock_recv": "print(__sock_recv(-1, 1))",
        "__sock_send_to": "print(__sock_send_to(-1, \"x\", \"\"))",
        "__sock_recv_from": "print(__sock_recv_from(-1, 1))",
        "__sock_addr": "print(__sock_addr(-1, 0))",
        "__sock_shutdown": "print(__sock_shutdown(-1, 3))",
        "__sock_option": "print(__sock_option(-1, 1, 1))",
        "__sock_poll": "print(__sock_poll(-1, 1, 0))",
        "__sock_close": "print(__sock_close(-1))",
        "__net_config": "print(__net_config(0))",
    }

    def check(self, source: str) -> tuple[str, int]:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, source)
            p = subprocess.run([selfhost_tool("main"), "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                               text=True)
            return p.stderr, p.returncode

    def test_each_is_a_warning(self):
        for name, call in self.CALLS.items():
            with self.subTest(name):
                src = f"fun main() {{\n    {call}\n}}\n"
                err, code = self.check(src)
                self.assertEqual(code, 0, err)
                self.assertIn(f"warning[primitive]: '{name}' is a primitive of the standard library", err)
                self.assertEqual(self.check("#allow(primitive)\n" + src), ("", 0))
                self.assertEqual(self.check(f"#allow(primitive({name}))\n" + src), ("", 0))

    def test_their_arguments_are_checked(self):
        cases = {
            "fun main() {\n    print(__sock_open(4))\n}\n": "__sock_open() takes (family: int, kind: int)",
            "fun main() {\n    print(__sock_bind(1, 2))\n}\n": "__sock_bind() takes (h: int, addr: str)",
            "fun main() {\n    print(__sock_recv(\"h\", 1))\n}\n": "__sock_recv() takes (h: int, n: int)",
            "async fun f() {\n    await __wait_socket(1)\n}\nfun main() {\n}\n": "__wait_socket() takes",
            "fun f() {\n    __wait_socket(1, 1)\n}\nfun main() {\n}\n": "needs 'await'",
        }
        for src, msg in cases.items():
            with self.subTest(msg):
                err, code = self.check(src)
                self.assertEqual(code, 1, err)
                self.assertIn(msg, err)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Primitives(unittest.TestCase):
    """The primitives directly: what a port to another system must give
    (docs/Language/Standard-library/Net.md)."""

    PROGRAM = """#allow(primitive)
fun e(r: int) -> str {
    return f"{r} {__io_errno()}"
}

#allow(primitive)
fun main() {
    let l = __sock_open(4, 1)
    print(l >= 0)
    print(e(__sock_bind(l, "\\u{4}\\u{0}\\u{0}\\u{7f}\\u{0}\\u{0}\\u{1}")))
    print(e(__sock_listen(l, 4)))
    let me = __sock_addr(l, 0)
    print(f"{me.len()} {me[0]} {me[3]} {me[6]}")
    print(e(__sock_set_nonblocking(l, 1)))
    print(e(__sock_accept(l)))
    print(e(__sock_poll(l, 1, 0)))
    let c = __sock_open(4, 1)
    print(e(__sock_set_nonblocking(c, 1)))
    let r = __sock_connect(c, me)
    print(r == 0 || __io_errno() == 115)
    print(__sock_poll(c, 2, 1000))
    print(e(__sock_error(c)))
    let s = __sock_accept(l)
    print(s >= 0)
    print(e(__sock_send(c, "hello", 1)))
    print(__sock_poll(s, 1, 1000))
    print(__sock_recv(s, 100))
    print(e(__sock_set_nonblocking(s, 1)))
    print(e(__sock_recv(s, 100).len()))
    print(e(__sock_addr(c, 1).len()))
    print(e(__sock_option(c, 1, 1)))
    print(e(__sock_option(c, 9, 1)))
    print(e(__sock_shutdown(c, 2)))
    print(__sock_poll(s, 1, 1000))
    print(e(__sock_recv(s, 100).len()))
    print(e(__sock_send(c, "x", 2)))
    print(e(__sock_close(c)))
    print(e(__sock_close(s)))
    print(e(__sock_close(l)))
    print(e(__sock_open(5, 1)))
    print(e(__sock_open(4, 3)))
    print(e(__sock_close(-1)))
    print(e(__sock_bind(__sock_open(4, 2), "nonsense")))
    let u = __sock_open(4, 2)
    print(e(__sock_bind(u, "\\u{4}\\u{0}\\u{0}\\u{7f}\\u{0}\\u{0}\\u{1}")))
    print(e(__sock_set_nonblocking(u, 1)))
    print(e(__sock_recv_from(u, 10).len()))
    print(e(__sock_send_to(u, "dgram", __sock_addr(u, 0))))
    let d = __sock_recv_from(u, 3)
    print(f"{d.len()} {d[0]} {d[19:]}")
    print(e(__sock_close(u)))
}
"""
    OUT = """true
0 0
0 0
7 4 127 1
0 0
-1 11
0 0
0 0
true
2
0 0
true
4 0
1
ello
0 0
0 11
7 0
0 0
-1 22
0 0
1
0 0
-1 22
0 0
0 0
0 0
-1 97
-1 22
-1 9
-1 22
0 0
0 0
0 11
5 0
22 4 dgr
0 0
"""

    def test_each_on_its_own(self):
        self.assertEqual(run_both(self.PROGRAM), (self.OUT, "", 0))

    def test_the_configuration(self):
        out, err, code = run_both("#allow(primitive)\nfun main() {\n    print(__net_config(0))\n"
                                  "    print(__net_config(7).len())\n}\n")
        self.assertEqual((out, err, code), ("/etc/hosts\n0\n", "", 0))


if __name__ == "__main__":
    unittest.main()
