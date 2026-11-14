---
id: MYLA-708
title: "Windows step 9: a job on a Windows runner"
type: feature
status: todo
priority: medium
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). D212: Wine isn't Windows; a `windows-latest` job runs what Wine can't prove, as `bootstrap-arm64` does for aarch64.

- [ ] CI builds the programs on Linux for `x86_64-windows` and runs the examples, the stress programs and the console and process cases on the Windows runner
- [ ] The x86-64 Windows `myla.exe` and `myla-lsp.exe` uploaded as artifacts on master (D207)
