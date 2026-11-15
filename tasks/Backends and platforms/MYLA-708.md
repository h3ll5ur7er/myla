---
id: MYLA-708
title: "Windows step 9: a job on a Windows runner"
type: feature
status: todo
priority: medium
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). D213: Wine isn't Windows; a `windows-latest` job runs what Wine can't prove, as `bootstrap-arm64` does for aarch64.

- [ ] CI builds the programs on Linux for `x86_64-windows` and runs the examples, the stress programs and the console and process cases on the Windows runner
- [ ] The x86-64 Windows `myla.exe` and `myla-lsp.exe` uploaded as artifacts on master (D207)

## What MYLA-702 couldn't check under Wine

- A read of the standard input with a time limit (`Reader.ready(ms)`, std.platform's `poll_read`) asks a pipe how much it holds (`PeekNamedPipe`) until the limit. Under Wine the pipe a Linux parent hands over isn't a named pipe, so the call fails and the read is taken for ready (it then blocks): the limit is to be checked on the runner.
- A frame larger than a page ([[MYLA-717]]): Wine maps the whole stack.
