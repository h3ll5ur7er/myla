---
id: MYLA-727
title: "std.process's own cases need POSIX tools: excused on Windows"
type: improvement
status: todo
priority: low
labels: [platforms, windows, stdlib, testing]
---
Found by [[MYLA-705]]. The `#test` cases of [[lib/std/process.my]] start `cat`, `sh`, `head`, `tr`, `wc`, `printf`, `sleep` and `true`. A Windows program can't find them, and Wine, given one by its path, starts it without the standard handles or the exit code it was given. Before MYLA-705 the cases returned at the first spawn's `Unsupported`; now that spawn is `NotFound`. So `tests/burn/_targets.py` excuses `std.process` from `test_std_modules` on x86_64-windows, and its target-independent cases (`SpawnError`'s messages, `spawn_error_from_cause`, `stdio_letters`, …) with it. test_process's `WindowsChildren` covers the same ground with a Windows program of its own.

- [ ] The cases' children are programs every target has: the harness's own executable in a mode of its own, or a helper that std.test builds, so the cases run on Windows too
- [ ] `std.process` no longer excused on x86_64-windows
