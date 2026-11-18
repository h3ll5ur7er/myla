---
id: MYLA-862
title: "Linux's run_with takes a failed read of a child's pipe for its end"
type: bug
status: todo
priority: low
labels: [platforms, stdlib]
---
Found by [[MYLA-798]], which made a read of a child's pipe that fails `Other` of its cause in std.process's `collect_async` ([[lib/std/process.my]]) and in Windows' `run_with` ([[lib/std/platform_windows.my]]). Linux's `run_with` ([[lib/std/platform.my]], and its aarch64 copy) still reads the two pipes with `read_some`, which gives -1 "at the end of the file or on an error": a pipe that fails to read ends that stream, and `run` and `output` give `Ok` with the output cut short and nothing said. On Linux a read of a pipe hardly fails (EIO, ENOMEM), which is why it is low.

- [ ] `read_some` tells the end from an error, and `run_with` records the first error's cause as the run's (`__set_run_status(code, sig, cause)`), as Windows' does
- [ ] the same in `platform_aarch64.my`; a `#test` or a burn test where one can be made to fail (a descriptor closed under it)
