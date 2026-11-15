---
id: MYLA-706
title: "Windows step 7: the poller on IOCP, and sockets over Winsock"
type: feature
status: todo
priority: medium
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). The reactor (D124) on I/O completion ports, through the platform interface; `std.net` over `ws2_32` (its seams are Windows-ready, [[Language/Standard-library/Net#porting-sockets-to-another-system]]).

- [ ] Descriptor waits, timers and tasks on IOCP
- [ ] TCP, UDP and name lookup; test_net and test_http pass under Wine

## What MYLA-703 left for this step

- The poller has timers only: `poller_new` gives a word in a cell of its own, `poller_wait` waits on it with `WaitOnAddress` for the nearest timer's time limit, and `poller_wake` (a frame pushed, a nearer timer) sets it and wakes the waiter with `WakeByAddressSingle` ([[lib/std/platform_windows.my]]). IOCP replaces the word: `PostQueuedCompletionStatus` is the wake.
- A read of the standard input that would suspend a task (`read_line_async`) blocks its worker; the other workers run the other tasks meanwhile.
