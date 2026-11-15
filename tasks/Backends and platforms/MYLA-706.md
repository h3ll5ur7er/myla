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
