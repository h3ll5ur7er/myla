---
id: MYLA-726
title: "Windows: a task writing to a child's full input pipe blocks the one worker"
type: bug
status: todo
priority: medium
labels: [platforms, windows, concurrency]
---
Found by [[MYLA-705]]. `ChildStdin.write_async` waits for room only when `__poll_write` says there is none, and Windows' `poll_write` always says there is: an anonymous pipe tells nobody how much room it has (that is `NtQueryInformationFile`'s, and D212 leaves ntdll out). So a task that writes more than the pipe holds (64 KiB asked of `CreatePipe`) to a child that writes its output before it reads further blocks in `WriteFile`, and with it the one worker: the task that would read the child's output never runs. That is MYLA-340's deadlock, which `write_async` prevents on Linux and wasm32.

Reproduction: std.process's own case `input_written_while_output_read` with a Windows `cat` (tests/burn/test_windows.py's `HELPER` in its `cat` mode, `./helper.exe`): `command("./helper.exe").arg("cat").spawn()`, then `async let wrote = feed(w, 10, 59999)` (10 lines of 60,000 bytes through `write_async`) beside `async let got = drink(r)` (`buffered(r).read_to_end_async()`), both awaited. Under Wine it never ends: `timeout 30` stopped it (124, 2026-11-15); on Linux the case passes.

- [ ] `write_async` on Windows waits for room with the task suspended: the child's input an overlapped named pipe written through the I/O completion port of [[MYLA-706]] (or a write of a piece the pipe is known to take)
- [ ] The case runs on Windows, with a Windows child
