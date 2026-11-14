---
id: MYLA-704
title: "Windows step 5: files, directories and paths"
type: feature
status: todo
priority: medium
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). D214: UTF-8 in Myla, UTF-16 at the API (`CreateFileW`, `FindFirstFileW`); `std.path` takes `/` and `\` and drive letters.

- [ ] std.fs over the Windows API through the platform interface of [[MYLA-701]]
- [ ] std.path on Windows paths: separators, drive letters, UNC paths; the docs say what differs
- [ ] test_fs and the file parts of the suites pass under Wine
