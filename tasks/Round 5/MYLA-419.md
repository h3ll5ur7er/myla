---
id: MYLA-419
title: "P5 Runtime handles, notifiers, timers, child streams, sockets"
type: bug
status: todo
priority: high
labels: [runtime, concurrency, process, net, round-5]
---
Work package P5 of [[Project/Review-2026-11-09]] (wave A2), with round 4's additions from [[Project/Review-2026-11-10]]. Files: the notifier and timer section of `lib/std/rt.my`, `lib/std/task.my`, `lib/std/process.my`, `lib/std/net.my`, the handle types in `lib/std/fs.my`, the platform modules where a handle is made.

- [ ] D181: handles as table indices with a generation for `Notifier` (H8), `TcpStream`, `TcpListener`, `UdpSocket` (M13), `File` and `Child`
- [ ] M10: a notifier is freed with its last handle, or pooled (a reply channel per request leaks about 50 bytes)
- [ ] M11: waking a wait with a time limit without a scan of every timer (`timers_forget`)
- [ ] M12: writing a child's stdin while reading its stdout doesn't deadlock on one worker or interpreted (an async write, a `Pollable` `ChildStdin`) ([[MYLA-340]])
- [ ] [[MYLA-378]]'s follow-up: a bad `cwd`, and a NUL in a program's name, are their own errors, not "program not found"
- [ ] D180: an async line reader over a socket in std.net, which doesn't block its worker
- [ ] S4: `read_line_async` on a non-blocking stdin with no other task waits natively as it does interpreted
- [ ] D184 for the modules of this package
- [ ] [[MYLA-351]]'s and [[MYLA-387]]'s follow-ups are the items above
