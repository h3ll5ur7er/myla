---
id: MYLA-780
title: "Windows' runner: std.process's own cases on Windows itself"
type: improvement
status: backlog
priority: low
labels: [platforms, windows, testing, ci]
---
Found by [[MYLA-727]]. std.process's 51 `#test` cases start the test tool (`<harness> --test-tool <step>…`, std.test's `tool_mode`) since MYLA-727, so they run for x86_64-windows: `myla test lib/std/process.my --target x86_64-windows` passes 51 of 51 under Wine, and `scripts/test-target.py x86_64-windows` runs them in `test_std_modules`. Wine isn't Windows (D213): its pipes, `TerminateProcess` and the console differ in places, and [[MYLA-708]]'s runner (`scripts/windows-runner.py`, CI's `windows` job) runs only its own cases on Windows itself, `process/std-process` among them, not std's.

- [ ] `windows-runner.py build` builds std.process's harness (`myla build` of the harness `myla test --native` makes, or a `myla.exe test lib/std/process.my --native` case once the job has LLVM's tools), and `run` runs it on Windows, each case reported
- [ ] Once [[MYLA-723]] gives an interpreted program the host's own modules, `myla.exe test lib/std/process.my` interpreted there too (under Wine it passes 49 of 51 before MYLA-723: the interpreter's `std.platform.TARGET` is Linux's, so `child_killed` and `pipeline_cut_short` expect Linux's statuses)
