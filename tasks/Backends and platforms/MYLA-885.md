---
id: MYLA-885
title: "The poller in Myla's terms: what MYLA-716 left"
type: refactor
status: backlog
priority: low
labels: [platforms, runtime, poller]
---
The box [[MYLA-716]] left open when it was signed off ([[Project/Review-2026-11-17]]); its other open box is [[MYLA-758]]. Under D209, the platform interface in Myla's terms; Windows' poller ([[MYLA-706]], D236) is built on the shape as it is, so nothing waits for this.

`poller_watch`, `poller_watch_socket` (`again`: armed once more, EPOLLONESHOT's shape), `poller_event(i)` and `poller_event_ready(i)` over a buffer of the last wait are epoll's form; wasm32 builds it on `poll_oneoff` (a legitimate implementation, not a translation: it stays), Windows will on IOCP ([[MYLA-706]]). A `POLLER` capability, and a wait that gives `(token, ready)` pairs, would let a target without one (and the interpreter) say so. `park` and `unpark_one` are futex's (`addr`, `seen`): wasm32's do nothing, as one worker needs; Windows' are `WaitOnAddress`/`WakeByAddressSingle`, the same shape, so they can stay.

- [ ] A `POLLER` capability, so that a target without a poller, and the interpreter, can say so
- [ ] A wait that gives `(token, ready)` pairs, in place of `poller_event(i)` and `poller_event_ready(i)` over a buffer of the last wait
- [ ] The four platform modules and the interpreter's primitives changed together (`test_platform_interface`)
