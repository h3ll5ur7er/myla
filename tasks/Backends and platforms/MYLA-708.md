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
- A frame larger than a page ([[MYLA-717]]): Wine maps the whole stack. `tests/burn/test_windows.py`'s `FramesOnWindows` (a recursion through a 64 KiB frame on the main thread and a worker) is skipped under Wine and runs where `sys.platform` is `win32`.

## What MYLA-707 couldn't check under Wine

[[MYLA-707]]'s console cases for this job are `RUNNER_CASES` in [[tests/burn/test_windows.py]]: each runs that file's `CONSOLE` program, built for Windows as `console.exe`, in a console of its own (`CREATE_NEW_CONSOLE`), its input that console and its output a file, as `cmd /c "console.exe ARGS > out.txt"` gives; the driver attaches to the console (`AttachConsole`, after `SetConsoleCtrlHandler(NULL, TRUE)` so that its own events don't end it), types keys into it (`WriteConsoleInputW` on `CONIN$`), sends `GenerateConsoleCtrlEvent(event, 0)` or closes the console's window (`WM_CLOSE` to `GetConsoleWindow()`), and compares the output file and the exit status. If `cmd` itself ends on a console's event, the driver starts `console.exe` with `STARTF_USESTDHANDLES` instead: `CONIN$` its input, the file its output, the console's `CONOUT$` its error. The cases, each a program's arguments, its steps, and what it must print and exit with:

| Case | Arguments | Steps | Output | Exit |
| --- | --- | --- | --- | --- |
| Raw keys through `ENABLE_VIRTUAL_TERMINAL_INPUT` | `keys 8` | after `raw line …`: Up, Ctrl-C, `q`, Alt-x, F5, Delete, Escape, Enter; after `restored true`: `hello` Enter | `raw line 0 echo 0 processed 0 vt 512`, `key Up`, `key Ctrl(c)`, `key Char(q)`, `key Alt(x)`, `key F5`, `key Delete`, `key Escape`, `key Enter`, `restored true`, `line hello\r` | 0 |
| UTF-8 typed into a cooked read (input code page 65001) | `keys 1` | `x`; then `größe` Enter | `…`, `key Char(x)`, `restored true`, `line größe\r` | 0 |
| The window's size | `size`, after `mode con: cols=101 lines=33` | — | `stdin 101 33`, `stdout none`, `stderr 101 33` | 0 |
| A real Ctrl-C to a listener, then the default | `interrupted` | after `ready`: `CTRL_C_EVENT`; after `again`: `CTRL_C_EVENT` | `ready`, `got interrupt`, `again` | 0xC000013A |
| Ctrl-Break | `interrupted` | the same with `CTRL_BREAK_EVENT` | the same | 0xC000013A |
| Ctrl-C typed while a cooked read waits (`ERROR_OPERATION_ABORTED`: the read goes on) | `readline` | after `ready`: Ctrl-C typed; after `caught interrupt`: `hi` Enter | `ready`, `caught interrupt`, `line hi\r` | 0 |
| The console closed (Terminate, then the program's own exit within 5 s) | `close closed.txt`, `console.exe` alone | after `closed.txt` says `ready`: `WM_CLOSE` | `closed.txt`: `ready`, `got terminate` | 7, within 10 s |
| D192: Ctrl-Break while a child on the console is raw | `ctrl raw token` | after `child raw`: `CTRL_BREAK_EVENT` | `child raw`, `exited -1073741510 restored true` | 0 |
| D192 with a listener in the raw child first | `ctrl listen token` | after `child listening`: `CTRL_BREAK_EVENT`; after `child raw`: again | `child listening`, `child caught interrupt`, `child raw`, `exited -1073741510 restored true` | 0 |
| D187: every end of raw mode puts the console's mode back | `ends` | — | `return 0 restored true` … `fails 1 restored true`, `left 0 restored false` (nine lines, as `Console.test_every_end_restores_the_console`) | 0 |

The window's size and a real Ctrl-C are what Wine can't give at all; under Wine `Console` checks the rest with a pseudo-terminal as the console and a Unix SIGINT as Ctrl-C, but not virtual-terminal input, a Ctrl-Break, a close, `STATUS_CONTROL_C_EXIT` (Wine's default ends with 0) or a read a Ctrl-C ends.
