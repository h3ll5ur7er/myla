---
id: MYLA-707
title: "Windows step 8: the terminal and signals"
type: feature
status: todo
priority: low
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). D215: `SetConsoleMode` for raw mode and the size; Ctrl-C and the close event as SIGINT and SIGTERM through `SetConsoleCtrlHandler`.

- [ ] std.term and std.signal on the console API
- [ ] test_term's cases that Wine's console allows; the rest checked on the Windows runner ([[MYLA-708]])
