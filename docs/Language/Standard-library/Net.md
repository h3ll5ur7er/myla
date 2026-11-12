# std.net

TCP and UDP sockets, IP addresses and name lookup ([[MYLA-346]]). A socket is an opaque handle inside a `TcpListener`, `TcpStream` or `UdpSocket`, an index into the runtime's table of handles with a generation (D181): once a socket is closed, every copy of it fails with `Other(9)` (EBADF) and never reaches the socket that gets its descriptor next, nor does a handle built by hand; an address is a Myla value; a failure is an `IoError` with a portable cause. Nothing here is a file descriptor, so a port to another system (Windows next) changes the platform layer only ([[#porting-sockets-to-another-system]]). On wasm32 every operation is `Unsupported`: WASI preview 1 has no sockets. A lookup there finds an address itself and `localhost`, and nothing else (`NotFound`: no hosts file, no name server).

[TOC]

## Addresses

| Item | Meaning |
| --- | --- |
| `enum IpAddr { V4(uint8, uint8, uint8, uint8), V6(uint16 × 8) }` | An IPv4 address's four bytes, or IPv6's eight 16-bit groups. `Eq`, `Hash` (a map key) and `Format`: `192.168.0.1`; IPv6 in RFC 5952's short form, lower-case, the longest run of zero groups as `::`, an IPv4-mapped one as `::ffff:192.0.2.1`. Methods `is_ipv4()`, `is_ipv6()`, `is_loopback()`, `is_unspecified()`, `octets() -> [uint8]` (4 or 16, network order) |
| `struct SocketAddr { ip: IpAddr, port: int }` | An address and a port. `Eq`, `Hash`, `Format`: `127.0.0.1:80`, `[::1]:8080` |
| `addr(ip, port) -> SocketAddr` | The two together |
| `loopback()`, `loopback_v6()`, `unspecified()`, `unspecified_v6()` | `127.0.0.1`, `::1`, `0.0.0.0` and `::` (every address of the machine, to bind to) |
| `parse_ip(s: str) -> Result<IpAddr, AddrParseError>` | Dotted decimal (each part 0 to 255, no leading zeros), or IPv6's forms of RFC 4291: eight hex groups, `::` once, the last 32 bits dotted. No zone (`%eth0`) |
| `parse_addr(s: str) -> Result<SocketAddr, AddrParseError>` | `1.2.3.4:80` or `[v6]:port`; an IPv6 address without brackets is `MissingPort` |
| `enum AddrParseError { Empty, InvalidIp, InvalidPort, MissingPort }` | Why a text isn't one. `Eq`, `message()`, `Format` (D168) |

```myla
import std.net as net

fun main() {
    for s in ["10.0.0.1", "2001:DB8:0:0:1:0:0:1", "::ffff:192.0.2.1", "1.2.3"] {
        match net.parse_ip(s) {
            Ok(ip) => print(f"{ip} loopback {ip.is_loopback()}")
            Err(e) => print(f"{s}: {e}")
        }
    }
    match net.parse_addr("[::1]:8080") {
        Ok(a) => print(f"{a} is port {a.port} of {a.ip}")
        Err(e) => print(f"{e}")
    }
}
// output:
// 10.0.0.1 loopback false
// 2001:db8::1:0:0:1 loopback false
// ::ffff:192.0.2.1 loopback false
// 1.2.3: invalid IP address
// [::1]:8080 is port 8080 of ::1
```

## TCP and UDP

| Item | Meaning |
| --- | --- |
| `listen(a: SocketAddr) -> Result<TcpListener, IoError>` | Listening on `a` (port 0: one the system picks); the address is reused while old connections to it linger. `AddrInUse`, `AddrNotAvailable`. Up to 128 connections wait to be accepted |
| `listen_with(a, backlog: int)` | `listen` with up to `backlog` connections waiting to be accepted ([[MYLA-548]]: past the queue a burst of connects is refused or reset); the system may take fewer (Linux: `net.core.somaxconn`, 4096 by default). A `backlog` below 1 is a runtime error (D184) |
| `TcpListener`: `accept()`, `accept_async()` (async) | The next connection, a `TcpStream`; `set_timeout(ms)` bounds `accept`'s wait (`TimedOut`) |
| `TcpListener`: `local_addr()`, `close()` | Its address; closed (a second close is `Other(9)`, as every operation through a closed handle is, D181, and as a `File`'s is; it did nothing before [[MYLA-548]]) |
| `connect(a)`, `connect_timeout(a, ms)`, `connect_async(a)` (async) | A connection: `ConnectionRefused`, `HostUnreachable`, `NetworkUnreachable`, `TimedOut` |
| `connect_host(host: str, port: int)` | `lookup(host)`'s addresses tried in turn |
| `TcpStream` | A `Read` and a `Write` of `std.io` ([[Language/Standard-library/Io#streams]]): `copy` and `read_all` take it, and `buffered(s)` reads its lines outside tasks (in a task it blocks its worker: use `line_reader`). A read gives what one receive gives, `[]` at the end of the stream; a write sends every byte. A copy is the same connection, and `close` closes it for every copy; a second close, through it or a copy, is `Other(9)` |
| `TcpStream`: `read_async(n)`, `write_async(b)` (async) | The read and the write, the task waiting; bytes, as `Read` and `Write` deal in (D177) |
| `TcpStream`: `peer_addr()`, `local_addr()`, `shutdown(how)`, `set_nodelay(on)`, `set_read_timeout(ms)`, `set_write_timeout(ms)`, `close()` | `how` is `Shutdown.Read`, `Write` or `Both`; after `Write` the peer reads the end. A timeout (negative: none, the default) makes a blocking wait `TimedOut` |
| `line_reader(s: TcpStream) -> LineReader` | Lines of text from `s` (D180), of any length: a peer that never sends `"\n"` makes it hold all it sends, about three times its size (a 512 MiB line: 1.59 GB) |
| `line_reader_with(s, max_line: int) -> LineReader` | Lines of at most `max_line` bytes, without their `"\n"` ([[MYLA-548]]): a longer one is `InvalidData` once more than `max_line` bytes of it are there, and so is every read after it, so the reader holds no more than about `max_line` and a read's 4 KiB (a peer sending 64 MiB without `"\n"` to a limit of 1 MiB: 5.9 MB, where `line_reader` peaked at 230 MB). A negative `max_line` is a runtime error (D184) |
| `LineReader`: `read_line_async()` (async), `read_line()` | The next line without its `"\n"` (a `"\r"` before it kept, as `io.Buffered.read_line` keeps it), a last line without one too, which `cut_off()` then tells apart; `None` at the end of the stream. The async form waits with the task suspended, as `read_async` does; a cancelled task gets `Cancelled`, the bytes read so far kept. Each byte is copied a bounded number of times, however long its line |
| `LineReader`: `cut_off()` | Whether the line given last ended at the end of the stream without a `"\n"`: a peer that closed in the middle of a line ([[MYLA-548]]) |
| `LineReader`: `rest()` | The bytes read past the last line given (a body after a protocol's header lines), taken out of the reader |
| `udp_bind(a) -> Result<UdpSocket, IoError>` | A UDP socket bound to `a` |
| `UdpSocket`: `send_to(b, to)`, `send_str_to(s, to)` | One datagram: its length |
| `UdpSocket`: `recv_from(n)`, `recv_str_from(n)`, `recv_from_async(n)`, `recv_str_from_async(n)` (async) | The next datagram, at most `n` bytes of it (the rest dropped), and its sender |
| `UdpSocket`: `local_addr()`, `set_read_timeout(ms)`, `set_broadcast(on)`, `close()` | A second close is `Other(9)` |

An async form waits with the task suspended and the other tasks running, on the reactor (D124): `accept_async`, a connect in progress, a read with nothing there yet, a write with the buffer full. Outside a task it blocks, as its twin does. A task asked to stop (`task.cancel`, `task.timeout`) stops waiting and gets `Cancelled`. A failure is an `IoError` ([[Language/Standard-library/Fs]]), whose network causes are `ConnectionRefused`, `ConnectionReset`, `ConnectionAborted`, `NotConnected`, `AddrInUse`, `AddrNotAvailable`, `TimedOut`, `HostUnreachable`, `NetworkUnreachable` and `InvalidData`; a peer that went away mid-write is `BrokenPipe` or `ConnectionReset`, an IPv6 the machine lacks `Unsupported`.

```myla
import std.net as net
from std.net import TcpListener
import std.bytes as bytes

async fun echo_once(l: TcpListener) -> int {
    var s = match await l.accept_async() {
        Ok(s) => s
        Err(e) => { return -1 }
    }
    var n = 0
    while true {
        let chunk = match await s.read_async(4096) {
            Ok(c) => c
            Err(e) => { return -1 }
        }
        if chunk.len() == 0 {
            break
        }
        n += chunk.len()
        let w = await s.write_async(chunk)
    }
    let c = s.close()
    return n
}

#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("can't listen") }
    }
    let at = match l.local_addr() {
        Ok(a) => a
        Err(e) => { panic("no address") }
    }
    async let served = echo_once(l)
    var s = match await net.connect_async(at) {
        Ok(s) => s
        Err(e) => { panic("can't connect") }
    }
    let w = await s.write_async(bytes.from_str("ping"))
    match await s.read_async(10) {
        Ok(back) => print(bytes.to_str(back))
        Err(e) => print("no answer")
    }
    let sh = s.shutdown(net.Shutdown.Write)
    print(await served)
    let c = s.close()
    let d = l.close()
}
// output:
// ping
// 4
```

A line protocol in tasks reads through a `LineReader` and writes to the stream itself, a copy of which is the same connection. `io.buffered(s).read_line()` would block its worker until the line came, and with one worker (`MYLA_THREADS=1`, a machine of one CPU, the interpreter) the peer never ran:

```myla
import std.net as net
from std.net import TcpListener, TcpStream
import std.bytes as bytes

async fun shout(l: TcpListener) -> int {
    var s = match await l.accept_async() {
        Ok(s) => s
        Err(e) => { return -1 }
    }
    var lines = net.line_reader(s)
    var n = 0
    while let Ok(Some(line)) = await lines.read_line_async() {
        let w = await s.write_async(bytes.from_str(line.to_upper() + "\n"))
        n += 1
    }
    let c = s.close()
    return n
}

#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("can't listen") }
    }
    let at = match l.local_addr() {
        Ok(a) => a
        Err(e) => { panic("no address") }
    }
    async let served = shout(l)
    var s = match await net.connect_async(at) {
        Ok(s) => s
        Err(e) => { panic("can't connect") }
    }
    var back = net.line_reader(s)
    for word in ["ping", "pong"] {
        let w = await s.write_async(bytes.from_str(word + "\n"))
        match await back.read_line_async() {
            Ok(Some(line)) => print(line)
            _ => print("no answer")
        }
    }
    let sh = s.shutdown(net.Shutdown.Write)
    print(await served)
    let c = s.close()
    let d = l.close()
}
// output:
// PING
// PONG
// 2
```

## Names

Without libc there is no getaddrinfo: `lookup` reads the hosts file, then asks the name servers over UDP (RFC 1035), an A query and then an AAAA one.

| Item | Meaning |
| --- | --- |
| `lookup(name: str) -> Result<[IpAddr], IoError>` | `system_resolver().lookup(name)` |
| `struct Resolver { hosts_path: str, servers: [SocketAddr], timeout_ms: int, attempts: int }` | Where to look: the hosts file (`""`: none), then the name servers, each query waited for `timeout_ms` (2000) and tried `attempts` times (2) |
| `system_resolver()`, `resolver(hosts_path, servers)` | The system's (its hosts file and the `nameserver` lines of its resolver's configuration, as the platform gives them: on Linux `/etc/hosts` and `/etc/resolv.conf`), or one of your own |
| `Resolver`: `lookup(name)` | An address itself; else the hosts file's entries for the name (its case ignored, a trailing dot allowed, Windows' line ends too); else, for `localhost` and the names below it (`db.localhost`), `127.0.0.1` and `::1`, as RFC 6761 has them, with no hosts file too ([[MYLA-426]]); else the first server's answer, IPv4's addresses first. `NotFound`: no such name, or no records, or no server to ask; `TimedOut`: no server answered; `InvalidData`: none gave a usable answer; `InvalidInput`: a name DNS can't carry (an empty label, one past 63 bytes, a name past 253). A reply from elsewhere or with another id is ignored |
| `hosts_lookup(text, name) -> [IpAddr]`, `nameservers(text) -> [SocketAddr]` | The two parsers, for a hosts file's and a resolv.conf's text |

`ask_one`, a method of `Resolver`, is `lookup`'s step, one query of one server, public only because a method can't be private yet ([[MYLA-433]]); a program has no need of it.

## Primitives

The module rests on these ([[MYLA-346]]), each a function of `std.rt` over `std.platform`'s socket functions, and in the interpreter the host's own. A handle is an `int`, an index into `std.rt`'s table of handles and the generation of its entry (D181), at least 2^23; the entry holds the platform's socket. An address crosses as a portable record, a string of 7 or 19 bytes: the family (4 or 6), the port (big-endian), the address's bytes. Each sets `__io_errno()` (0 on success), a Linux errno number on every target; a handle that isn't open (closed, a copy of a closed one, made up) is EBADF (9).

| Primitive | x86-64 and aarch64 Linux | Result |
| --- | --- | --- |
| `__sock_open(family, kind) -> int` | socket(2), `SOCK_CLOEXEC`; family 4 or 6, kind 1 (TCP) or 2 (UDP) | A handle, blocking; -1 (EAFNOSUPPORT, EINVAL) |
| `__sock_set_nonblocking(h, on) -> int` | ioctl(`FIONBIO`) | 0 or -1 |
| `__sock_bind(h, addr: str)`, `__sock_connect(h, addr)`, `__sock_listen(h, backlog)` | bind(2), connect(2), listen(2) | 0 or -1; a non-blocking connect is EINPROGRESS (115), done once writable |
| `__sock_accept(h) -> int` | accept4(2), `SOCK_CLOEXEC` | A new handle, blocking; EAGAIN when none is queued on a non-blocking one |
| `__sock_error(h) -> int` | getsockopt(`SO_ERROR`) | The pending error, taken (0: none) |
| `__sock_send(h, s, start) -> int`, `__sock_recv(h, n) -> str` | sendto(2) with `MSG_NOSIGNAL`, recvfrom(2) | Bytes sent; bytes received, `""` at the end; EAGAIN on a non-blocking one |
| `__sock_send_to(h, s, addr) -> int`, `__sock_recv_from(h, n) -> str` | sendmsg(2), recvmsg(2) | Bytes sent; the sender's record in 19 bytes, then the datagram |
| `__sock_addr(h, peer) -> str` | getsockname(2) (`peer` 0), getpeername(2) (1) | The record, `""` on an error |
| `__sock_shutdown(h, how)`, `__sock_option(h, opt, v)`, `__sock_close(h)` | shutdown(2) (1 read, 2 write, 3 both), setsockopt(2) (1 `TCP_NODELAY`, 2 `SO_BROADCAST`, 3 `SO_REUSEADDR`), close(2) | 0 or -1 |
| `__sock_poll(h, events, ms) -> int` | poll(2) (ppoll(2) on aarch64) | The events ready (1 receive or accept, 2 send or a connect's end; an error or a hang-up counts as both), 0 when `ms` ran out |
| `await __wait_socket(h, events)` | The reactor: epoll, the socket armed once with what its waiters wait for | The task waits; without tasks, `__sock_poll(h, events, -1)` |
| `__sock_lot(n: int64) -> int`, `__sock_park(lot, h, deadline: int64, tag: int64) -> int` | The reactor: a watch with no frame ([[MYLA-468]], std.http's kept connections) | A lot, whose sockets once readable notify the notifier `n` (a `Notifier`'s id) once each; `h` parked on it with its deadline and tag: how many are parked |
| `__sock_ready(lot) -> int`, `__sock_expired(lot, now: int64) -> int`, `__sock_tag(h) -> int64`, `__sock_lot_close(lot) -> int` | std.rt's (the interpreter's own) | The first socket that became ready; one whose deadline is `now` or before, the earliest (`now` negative: whatever its deadline); `h`'s tag; the lot closed (its sockets unwatched, not closed). 0 for none, -1 (EBADF) for a lot that isn't open |
| `__net_config(which) -> str` | `/etc/hosts` (0); `/etc/resolv.conf`'s text (1) | `""` for none |

On wasm32 each gives ENOSYS (38), `Unsupported`, and `__net_config` `""`.

## Porting sockets to another system

A port gives the socket functions of `std.platform` again (`sock_open`, `sock_nonblocking`, `sock_bind`, `sock_listen`, `sock_accept`, `sock_connect`, `sock_error`, `sock_send`, `sock_recv`, `sock_send_to`, `sock_recv_from`, `sock_addr`, `sock_shutdown`, `sock_option`, `sock_poll`, `sock_close`, `net_config`, and the poller's `poller_watch_socket`, `poller_forget_socket` and `poller_event_ready`) over its own interface; `std.rt` and `std.net` stay as they are. For Windows (`platform_windows.my`, over Winsock):

- **Handles.** A `SOCKET` is what the handle's entry in `std.rt`'s table holds (D181), where Linux's holds the descriptor. Sockets aren't file descriptors there, which is why data goes through send and receive, never read and write, and `sock_close` is `closesocket`, apart from a file's close. The entry holds a 64-bit word, so a `SOCKET` fits whatever its width. `WSAStartup` happens once, before the first socket.
- **Contract.** Each function gives 0 or more, or minus an errno, as on Linux: a socket starts blocking and `sock_nonblocking` is `ioctlsocket(FIONBIO)`; `sock_accept` gives a blocking socket (Winsock's inherits the listener's mode, so the port sets it back); `sock_send` doesn't raise a signal; `sock_recv_from` drops what a datagram has past `n` bytes (`WSAEMSGSIZE` is not an error); `sock_addr` and `sock_recv_from` write the portable record, never a `sockaddr`; option 3 (`SO_REUSEADDR`) does nothing, as Windows allows a lingering address anyway and its own `SO_REUSEADDR` would let another program take a port.
- **Errors.** `WSAGetLastError()`'s codes map onto Linux's numbers, which `std.fs`'s `from_errno` knows: `WSAEWOULDBLOCK` is EAGAIN (11), and EINPROGRESS (115) for a connect; `WSAECONNREFUSED` 111, `WSAECONNRESET` 104, `WSAECONNABORTED` 103, `WSAENOTCONN` 107, `WSAEADDRINUSE` 98, `WSAEADDRNOTAVAIL` 99, `WSAETIMEDOUT` 110, `WSAEHOSTUNREACH` 113, `WSAENETUNREACH` 101, `WSAEAFNOSUPPORT` 97, `WSAEINVAL` 22, `WSAENOTSOCK` and an invalid handle 9, `WSAEINTR` 4.
- **Readiness.** `sock_poll` is `WSAPoll` with the same meaning: 1 for `POLLRDNORM`, 2 for `POLLWRNORM`, and `POLLERR` or `POLLHUP` as both. The reactor's `poller_watch_socket(p, h, events, token, again)` arms a socket once for the union of what its waiters ask (`again`: it was watched before, and its watch fired: armed again rather than added), and a later wait gives `token` when it is ready, `poller_event_ready` what it is ready for; `poller_forget_socket` disarms it. A wake-up may come early, as the caller retries on EAGAIN. On Windows the poller would watch sockets with `WSAPoll` beside its wake-up event, or through IOCP (`AFD_POLL`, as libuv and mio do).
- **Configuration.** `net_config(0)` is `%SystemRoot%\System32\drivers\etc\hosts`; `net_config(1)` the name servers of `GetNetworkParams` as `nameserver` lines.
