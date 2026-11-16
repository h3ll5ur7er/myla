---
id: MYLA-726
title: "Windows: a task writing to a child's full input pipe blocks its worker"
type: bug
status: review
priority: medium
labels: [platforms, windows, concurrency]
---
Found by [[MYLA-705]]. `ChildStdin.write_async` waits for room only when `__poll_write` says there is none, and Windows' `poll_write` always says there is: an anonymous pipe tells nobody how much room it has (that is `NtQueryInformationFile`'s, and D212 leaves ntdll out). So a task that writes more than the pipe holds (64 KiB asked of `CreatePipe`) to a child that writes its output before it reads further blocks in `WriteFile`, and with it its worker. Since [[MYLA-703]] there are several workers, so another may run the task that reads the child's output; but with one (`MYLA_THREADS=1`, a machine of one CPU) or with every worker blocked so, that task never runs. That is MYLA-340's deadlock, which `write_async` prevents on Linux and wasm32 on any number of workers.

Reproduction: std.process's own case `input_written_while_output_read` with a Windows `cat` (tests/burn/test_windows.py's `HELPER` in its `cat` mode, `./helper.exe`): `command("./helper.exe").arg("cat").spawn()`, then `async let wrote = feed(w, 10, 59999)` (10 lines of 60,000 bytes through `write_async`) beside `async let got = drink(r)` (`buffered(r).read_to_end_async()`), both awaited. Under Wine it never ends with `MYLA_THREADS=1`: `timeout 30` stopped it (124, 2026-11-15); with 2 or 4 workers it ends (`600000 600000`), as on Linux on any number.

- [x] `write_async` on Windows waits for room with the task suspended: the child's input an overlapped named pipe written through the I/O completion port of [[MYLA-706]] (or a write of a piece the pipe is known to take)
- [x] The case runs on Windows, with a Windows child (test_windows' `Sockets.test_a_childs_input_written_while_its_output_is_read`, and CI's `windows` job as `process/input-while-output`; std.process's own case still runs Linux's `cat`, [[MYLA-727]])

## What changed

With [[MYLA-706]] a child's input is a named pipe whose end here is overlapped (`pipe_pair`). A write of it (`pipe_write`, [[lib/std/platform_windows.my]]) waits for the write before it to end, then writes a copy of what it is given (at most 256 KiB) overlapped and gives its length back, whether the write ended at once or goes on: the pipe's room is never asked, which Windows can't say, but a write that would wait goes on without its thread. `poll_write` of such a pipe is 1 once the write before has ended (its OVERLAPPED's status, waited for at most the time given), 0 before. So `write_async`'s `__poll_write(fd, 0)` is 0 while the pipe is full, its task waits in `__wait_writable` (`poller_watch_socket` with 2, which the port's poller serves for a pipe as for a socket: the write's end is a packet), and the worker runs the task that reads the child's output. A plain `write` waits as Linux's blocking one does. The write's failure (the child closed its input or ended) is the next write's `BrokenPipe`. A close while a write goes on would cancel it with its bytes: the pipe is closed by a wait of the thread pool's once the write has ended (`ws_close_later`), so the child reads every byte and then the end; one still going when the program ends is lost.

## Evidence

- **Test first**: the reproduction above (`INPUT_WHILE_OUTPUT` in tests/burn/test_windows.py, 10 writes of 60,000 bytes and a newline) built with BASE `9738e37`'s library and this branch's compiler, under Wine: `MYLA_THREADS=1` stopped by `timeout 30` (124), 4 workers `600000 600000 0` (2026-11-16).
- **On this branch**: `600000 600000 0` on 1, 2 and 4 workers (`Sockets.test_a_childs_input_written_while_its_output_is_read`; `scripts/windows-runner.py run --wine`'s `process/input-while-output`, 0.3 s).
