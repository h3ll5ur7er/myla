---
id: MYLA-346
title: "Sockets: primitives and std.net"
type: feature
status: review
priority: low
labels: [stdlib, net, primitives, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #47. The platform track's second task. WASI preview 1 has no sockets, so on wasm32 every call is `Unsupported`.

- **Owns:** `lib/std/platform*.my`, `selfhost/` (primitives), `lib/std/net.my`, `docs/Language/Standard-library/Net.md`
- **Needs:** [[MYLA-336]], [[MYLA-338]]

- [x] The primitives: socket, bind, listen, accept, connect, send, recv, close, set non-blocking; the reactor waits on them
- [x] `TcpListener`, `TcpStream` (a `Read` and `Write`), `UdpSocket`, addresses and their parsing
- [x] Name lookup through `/etc/hosts` and a DNS query over UDP
- [x] Async forms on the reactor

## Done (2026-11-08)

Seventeen primitives, each a function of `std.rt` over `std.platform`'s socket functions on x86-64, aarch64 and wasm32, and the host's own in the interpreter (`is_net_primitive` in the checker; the tables are on [[Language/Standard-library/Net#primitives]]): `__sock_open`, `__sock_set_nonblocking`, `__sock_bind`, `__sock_listen`, `__sock_accept`, `__sock_connect`, `__sock_error`, `__sock_send`, `__sock_recv`, `__sock_send_to`, `__sock_recv_from`, `__sock_addr`, `__sock_shutdown`, `__sock_option`, `__sock_poll`, `__sock_close`, `__net_config`; and the reactor's wait `await __wait_socket(h, events)` (std.rt's `wait_sock`; without tasks a blocking `__sock_poll`). A socket is a handle only these take: sent to and received from, closed apart from files, made non-blocking explicitly; an address crosses as a portable record (family, port, bytes), never a `sockaddr`. The reactor's watch table holds what each frame waits for (1 receive, 2 send), and the platform's new `poller_watch_socket` and `poller_forget_socket` arm a socket for the union of its waiters: writability came with them, for a connect in progress and a full send buffer. On wasm32 every one is ENOSYS, `Unsupported`.

`std.net` (`lib/std/net.my`): `IpAddr` (V4, V6) and `SocketAddr`, parsed and printed (RFC 4291 and 5952), `TcpListener`, `TcpStream` (a `Read` and `Write`), `UdpSocket`, their async forms (`accept_async`, `connect_async`, `read_async`, `read_str_async`, `write_async`, `write_str_async`, `recv_from_async`, `recv_str_from_async`), timeouts, and `lookup` through the hosts file and DNS over UDP (`Resolver`, `system_resolver`, `resolver`, `hosts_lookup`, `nameservers`). Its errors are `std.fs`'s `IoError`, which gained ten portable network causes (`ConnectionRefused`, `ConnectionReset`, `ConnectionAborted`, `NotConnected`, `AddrInUse`, `AddrNotAvailable`, `TimedOut`, `HostUnreachable`, `NetworkUnreachable`, `InvalidData`), mapped from errno by `from_errno`. What a Windows port must give is on [[Language/Standard-library/Net#porting-sockets-to-another-system]] and [[Language/Targets#sockets-on-another-system]].

No seed staging: the compiler imports `std.fs`, `std.io` and `std.process`, none of which calls a new primitive; std.rt's and std.platform's new functions are compiled only where a program calls them, and use only the raw-memory primitives the seed knows. `scripts/bootstrap.sh` from the unchanged seed reaches the fixed point.

## Evidence

- `tests/burn/test_net.py` (13 tests): addresses; a TCP echo between tasks on the reactor (two clients at once, an accept that waits while a sleeping task runs, a read `task.timeout` stops); the async forms in a program of one task (no reactor: the blocking poll); a listener in one program and a client in another, each interpreted and built (four pairs); UDP (sent, received, cut short, timed out, awaited, and over `::1` when the machine has it); a test hosts file; DNS against a fake name server the test runs on 127.0.0.1 UDP (A, AAAA, a CNAME, a stray reply with another id, NXDOMAIN, SERVFAIL, silence); a refused connection, an address in use (TCP and UDP), one not this machine's, accept and read timeouts, a closed stream; each primitive directly; the primitive warning and argument checks. Natively against the interpreter: 12 pass, `NetOnWasm` skipped. `scripts/test-target.py aarch64-linux test_net` (qemu): passes. `wasm32-wasi test_net` (Node): passes, the socket classes excused in `_targets.py` and `NetOnWasm` checking that `listen`, `connect`, `udp_bind` and a DNS lookup are `Unsupported`.
- `build/myla test lib/std/net.my --stdlib lib`: 94/94 interpreted, `--native`, `--target aarch64-linux` and `--target wasm32-wasi` (parsing, printing, records, hosts and resolv.conf text, DNS names, queries and answers). `lib/std/fs.my` 64/64, the three platform modules and `rt.my` pass.
- `scripts/test.sh fast`: 678 tests, OK. `test_platform_primitives`, `test_fs`, `test_process`, `test_stdio`, `test_time`, `test_selfhost_cases`, `test_compiler_parity`, `test_std_modules`, `test_doc_blocks`, `test_net`: 270 tests, OK.
- `scripts/bootstrap.sh`: byte-identical fixed point (15,951,868 bytes) from the unchanged seed.
- Measured natively, best of three (4-core machine shared with other lanes): 1 GiB through loopback TCP in 64 KiB writes and reads, one program, two tasks on the reactor: 437 ms, 2.45 GB/s (4 workers), 401 ms, 2.68 GB/s with `MYLA_THREADS=1`. 10,000 short connections (connect, accept, close both): 944 ms, 10,600 a second on 4 workers (the runs ranged from 3,400 to 10,600 under the machine's load), 901 ms, 11,100 a second on one worker.
