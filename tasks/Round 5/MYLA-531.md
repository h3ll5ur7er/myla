---
id: MYLA-531
title: "The poller takes at most four events a wait"
type: improvement
status: backlog
priority: low
labels: [runtime, concurrency, net, round-5]
---
Found by [[MYLA-518]] (lane R of the second follow-up batch). `std.platform`'s `poller_wait` (x86-64 and aarch64) gives `epoll_wait` room for four events (`__poll_buf + 48`, 12 or 16 bytes each, the buffer being 128 bytes), so a reactor with many descriptors ready at once (a server's parked connections, [[MYLA-468]], when many clients send at once) needs a wait, and a look at the poller, for each four. Each look is a system call and, from a busy worker, comes every 64 frames (`exec_run`'s glance), from an idle one every 512 turns of its spin.

```myla fragment
// lib/std/platform.my
let n = __syscall5(SYS_EPOLL_WAIT, p & LOW32, events, 4, timeout_ms, 0)
```

- [ ] A buffer for 64 or more events (the poller's own, from `poller_new`, so no runtime variable changes), `poller_event` and `poller_event_ready` reading it
- [ ] A measurement: many connections ready at once (lane D's four async clients against a server, or 64 clients each sending in a loop), requests a second before and after
