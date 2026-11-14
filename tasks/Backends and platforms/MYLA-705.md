---
id: MYLA-705
title: "Windows step 6: child processes"
type: feature
status: todo
priority: medium
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). `CreateProcessW` with a quoted command line, pipes for the standard streams, the program found through `PATH` and `PATHEXT` ([[MYLA-190]]); the exit code with 32 bits (D215).

- [ ] std.process: `run`, `command`, pipes, waiting, killing
- [ ] test_process passes under Wine; the exit code's 32 bits documented on [[Language/Targets]]
