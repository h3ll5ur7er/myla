---
id: MYLA-295
title: "Standard-library polish: task.cancel's signature, Command.env's name, tests for io, time, task and toml"
type: chore
status: backlog
priority: low
labels: [stdlib]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]).

- `task.cancel(child: int)` ([[lib/std/task.my]]) is still the fake signature the October review flagged: the compiler intercepts the call, and hover shows `int`
- `Command.env("A=B", "c")` yields `A=B=c`: the name isn't validated ([[lib/std/process.my]])
- `#test` coverage is zero in `io.my`, `task.my`, `time.my` and the 646-line `toml.my`; `rt.my` has 8 cases for 136 functions (`digit_count`, `str_hash`, `timer_sift`, `map_lookup` are pure); `ownership.my` has none
- `from_errno` maps `EPERM` to `PermissionDenied`, undocumented
- the `std.rt` paragraph of [[Language/Standard-library]] is one 400-word sentence; a table, or Architecture

- [ ] Each item
