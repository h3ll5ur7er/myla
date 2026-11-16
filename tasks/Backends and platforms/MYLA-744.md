---
id: MYLA-744
title: "Windows: std.signal's pipe looked at every millisecond while someone listens"
type: improvement
status: backlog
priority: low
labels: [platforms, windows, concurrency]
---
Found when wave 4's lanes were merged ([[MYLA-165]]). [[MYLA-707]]'s console control handler (`__win_on_ctrl`, [[selfhost/runtime_x86.my]]) writes a caught signal's number to an anonymous pipe (`CreatePipe`, `__sig_pipe`), which std.signal's reactor watches. [[MYLA-706]]'s poller waits on an I/O completion port, which can't wait on an anonymous pipe, so it looks at that pipe every millisecond while a program listens for signals: a program that only waits for Ctrl-C wakes a thousand times a second.

- [ ] The handler tells the poller without the per-millisecond look: e.g. it posts a packet to the port (`PostQueuedCompletionStatus`, a kernel32 call that needs no state block, the port's handle in a process word), or the pipe becomes a named pipe whose read end is overlapped, as a child's pipes are
- [ ] A program awaiting `std.signal` alone uses about no CPU under Wine (compared with this branch's, D197), and test_windows' `Console` cases pass on 1, 4 and 16 workers
