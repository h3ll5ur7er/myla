---
id: MYLA-346
title: "Sockets: primitives and std.net"
type: feature
status: backlog
priority: low
labels: [stdlib, net, primitives, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #47. The platform track's second task. WASI preview 1 has no sockets, so on wasm32 every call is `Unsupported`.

- **Owns:** `lib/std/platform*.my`, `selfhost/` (primitives), `lib/std/net.my`, `docs/Language/Standard-library/Net.md`
- **Needs:** [[MYLA-336]], [[MYLA-338]]

- [ ] The primitives: socket, bind, listen, accept, connect, send, recv, close, set non-blocking; the reactor waits on them
- [ ] `TcpListener`, `TcpStream` (a `Read` and `Write`), `UdpSocket`, addresses and their parsing
- [ ] Name lookup through `/etc/hosts` and a DNS query over UDP
- [ ] Async forms on the reactor
