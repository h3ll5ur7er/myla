---
id: MYLA-933
title: "On Windows a parked socket is closed with a reset: the keeper's 408 and the end of an idle kept connection don't reach the client"
type: bug
status: todo
priority: high
labels: [http, net, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24): on the native Windows runner (run 275 and the run before it, the same both times) two of test_http's server tests fail for the built server only; the interpreted server passes them, and so does Linux.

- `KeepAlive.test_idle_and_busy_connections_are_closed_in_time` (`server='built'`): after one answered request the connection idles past `keep_alive_ms` and the keeper closes it. The client's next `recv` gets `ConnectionResetError` (WSAECONNRESET, 10054) where it wants the end of the stream (`b""`).
- `TimeLimits.test_dribbled_heads_do_not_take_the_workers` (`server='built'`): 200 heads dribbled a byte at a time, parked. Once `read_ms` passes, the keeper's `dropped` sends `408 Request Timeout` and closes. A dribbler reads `b''` (`end_of` takes a reset for the end), not the 408.

Both are connections parked on the lot when the keeper closes them ([[lib/std/http.my#L3973-L3995]], `dropped`, `closed`). In a program with tasks a parked stream socket is on the completion port with a read of no bytes in flight (the overlapped `WSARecv` [[lib/std/platform_windows.my#L3220-L3260]] describes). `sock_close` ([[lib/std/platform_windows.my#L4577-L4606]]) waits for a send that is still going (`ws_close_later`) but calls `closesocket` while that receive is pending. Winsock closes a socket abortively when a receive is pending on it: it sends RST, not FIN. libuv says the same in `uv_tcp_close`, which shuts the socket down for sending first ("in order for winsock to do a graceful close there must not be any pending reads, or the socket must be shut down for writing"). On Windows the RST makes the client drop what it has received and not yet read (the 408), and its next `recv` fails with WSAECONNRESET. The interpreted server's sockets are not on a port (the interpreter is a program without tasks, so it uses plain non-blocking calls and `WSAPoll`), so its closes are graceful. That is why it passes. This is a likely cause, not yet proven: it was reasoned out from the code and the two runs' logs, and there is no Windows machine here to try it (Wine's sockets aren't Windows').

The tests are right and stay failing until this is fixed.

Also seen in the same runs, interpreted server only, cause not found (it may need a task of its own):
- `TimeLimits.test_idle_non_reading_and_slow_handled_connections` (`server='interpreted'`): a client that never reads (SO_RCVBUF 4096) still gets the whole 8 MiB response (`8388652 not less than 8388608`) when it reads 2 s later. The server didn't cut it after `write_ms` (300) without progress; the built server does.
- `ToTheLimit.test_the_servers_count_is_what_its_clients_got`: in the interpreter, `serve_n` counts the 8 MiB answer to the client that closed unread (MYLA-863's case). Output: `ask 19: timed out, 19 answered before`, `client 19 of 20, server 20`. Built, it prints `client 20 of 20, server 20`.
Both are a large response to a peer that doesn't read it, sent with Winsock's plain non-blocking `send` (no port). One to look at: whether Windows' `send` takes far more than the socket's buffer at once, so the server sees the whole response go.

- [ ] `sock_close` on Windows closes a socket with a receive in flight gracefully (`shutdown(SD_SEND)` first, or the receive cancelled and its end waited for before `closesocket`), so that what was sent reaches the peer before the FIN
- [ ] Evidence: KeepAlive and `test_dribbled_heads_do_not_take_the_workers` pass for the built server on the `burn-windows` job; on Linux nothing changes
- [ ] The interpreted server's two failures above diagnosed on Windows (fixed here or given a task of their own)
