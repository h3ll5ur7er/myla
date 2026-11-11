---
id: MYLA-419
title: "P5 Runtime handles, notifiers, timers, child streams, sockets"
type: bug
status: review
priority: high
labels: [runtime, concurrency, process, net, round-5]
---
Work package P5 of [[Project/Review-2026-11-09]] (wave A2), with round 4's additions from [[Project/Review-2026-11-10]]. Files: the notifier and timer section of `lib/std/rt.my`, `lib/std/task.my`, `lib/std/process.my`, `lib/std/net.my`, the handle types in `lib/std/fs.my`, the platform modules where a handle is made.

- [x] D181: handles as table indices with a generation for `Notifier` (H8), `TcpStream`, `TcpListener`, `UdpSocket` (M13), `File` and `Child`
- [x] M10: a notifier is freed with its last handle, or pooled (a reply channel per request leaks about 50 bytes)
- [x] M11: waking a wait with a time limit without a scan of every timer (`timers_forget`)
- [x] M12: writing a child's stdin while reading its stdout doesn't deadlock on one worker or interpreted (an async write, a `Pollable` `ChildStdin`) ([[MYLA-340]])
- [x] [[MYLA-378]]'s follow-up: a bad `cwd`, and a NUL in a program's name, are their own errors, not "program not found"
- [x] D180: an async line reader over a socket in std.net, which doesn't block its worker
- [x] S4: `read_line_async` on a non-blocking stdin with no other task waits natively as it does interpreted
- [x] D184 for the modules of this package
- [x] [[MYLA-351]]'s and [[MYLA-387]]'s follow-ups are the items above

## What was built

**The handle table (D181).** `std.rt` keeps one table, `__handles` (a new runtime variable: the table's cell and its lock, staged in the seed). A handle is a positive `int`: its entry's index in the low bits (the table has a power of two entries) and a count above them, so the entry holds its whole number while it is open and 0 once free. Handles are given in increasing order from 2^23, the first number past the last one given whose entry is free, so a closed handle's number isn't given again for some two billion handles, and no descriptor or process ID (Linux's are below 2^20 and 2^22) is one. The table doubles before it is half full, each entry moving to its handle's place modulo the new size (two open handles differ modulo the old size). An entry is `[handle][kind][value]`: the kind (socket, notifier, descriptor) keeps one kind's handle from being used as another's, and the value is what the platform uses: a descriptor on Linux, a `SOCKET` on a Windows port, a record's address for a notifier. std.net still calls nothing a descriptor.

- **Notifiers.** `__notifier()` gives a handle for the record; every primitive looks it up under the timers' lock. `Notifier.close()` is new: it wakes the waiters (their waits give false) and frees the record. A use of a closed notifier through any copy, a second close, and a `Notifier` built by hand are the runtime error `use of a closed notifier` (std.task panics on the primitive's answer, so both runners report it alike). The interpreter's notifiers have a generation of their own (`(count << 20) | slot`).
- **Sockets.** `__sock_*` take and give handles; a handle that isn't open is EBADF (`Other(9)`), so a copy of a closed `TcpStream` no longer writes into, or closes, the socket that got its descriptor.
- **`File` and `Child`.** `__open` and `__spawn_piped` give handles for a file's descriptor and a child's pipes and pidfd. The descriptor primitives (`__read`, `__read_bytes`, `__write`, `__write_bytes`, `__seek`, `__fstat`, `__poll`, `__poll_write`, `__close`, the waits) take a handle for the descriptor it holds, or a number below 2^23 as a descriptor itself, so `io.fd_stream`, the standard streams and std.io's `Pollable` stay as they are. `File`, `ChildStdin`, `ChildStdout` and `ChildStderr` refuse a number below 2^23 (one built by hand), and `Child.kill` through a copy whose child another copy reaped signals nothing (its pidfd's handle is closed), where the process ID might be another process's by then.
- **What remains**: a close on one worker racing an operation through a copy on another can still let that operation's system call reach a descriptor reused in between (the look-up and the call aren't one step). Closing a stream another task is using is the program's race; a fix would count the operations in flight per entry and defer the close, as Go's `fdMutex` does.

**M10.** A notifier can't be freed with its last copy (Myla has no destructors), so the leak is closed where it came from: a channel makes a notifier per waiter and closes it when the waiter's slot is freed (after it settled), so a channel nobody waits on holds no notifier. A notifier a program makes and never closes still lives on (now about 60 to 90 bytes with its table entry, the table being at most half full); `close` frees it.

**M11.** A wait's time limit keeps its place in the timers' heap in its waiter (`timer_placed`, called wherever an entry moves), so a wake takes it off in O(log n) (`timer_remove`) instead of `timers_forget`'s scan and a heapify. A deadline's end and a cancel still scan ([[MYLA-456]]).

**M12.** `ChildStdin.write_async(b)` waits for room with the task suspended (`await __wait_writable(fd)`, a new primitive; natively the poller watches the descriptor for writing, interpreted the host's `__poll_write`), then writes PIPE_BUF bytes, which a pipe with room takes without blocking. `ChildStdin` is `Pollable`.

**MYLA-378's follow-up.** The child reports a failed chdir's errno plus 4096 (`DIR_FAILED`), which std.process turns into `SpawnError.WorkingDir(errno)`; a NUL byte in the program's name, an argument or the directory is `InvalidInput` before anything runs.

**D180.** `net.line_reader(s)` gives a `LineReader`: `read_line_async()` (the task waits in `read_async`), `read_line()` (its blocking twin) and `rest()` (the bytes past the last line). A `"\r"` is kept, as `io.Buffered.read_line` keeps it; each byte is copied a bounded number of times however long its line.

**S4.** Without tasks, `await __wait_readable(fd)` and `__wait_writable(fd)` block the thread until the descriptor is ready (`wait_alone`), as the interpreter waits; they lowered to nothing, so the read of a non-blocking stdin gave EAGAIN.

**D184.** In std.net a port outside 0 to 65535 (`net.addr`, or any `SocketAddr` a socket call gets) is the runtime error `port 65536 out of range (0 to 65535)`, where the address record kept its low 16 bits. The parsers of outside input here (addresses, hosts files, resolv.conf, DNS replies) already return their errors for numbers out of range; the rest of the package's arithmetic is on numbers the runtime makes.

## Proposals (open decisions)

1. **`SpawnError.WorkingDir(int32)`** for a directory `cwd` gave that can't be entered, with its errno; built. Alternatives: `NotFound` as before (Rust's choice, which can't be told from a missing program), or `Other(errno)` (no new variant, but `Other` is "anything else"). A new variant breaks an exhaustive `match` on `SpawnError` (`examples/subprocess` had one). Recommended: the variant.
2. **`Notifier.close()` and "use of a closed notifier"** as a runtime error for any use after the close, a wait that starts after it included; a wait already parked when the close comes ends with false. Built. Alternative: a wait or a wake on a closed notifier gives false or does nothing (no error), which would make a close racing a waiter's start benign but hides a forged or stale handle, against D181's "a runtime error for a notifier". Recommended: as built.
3. **M10 by closing per waiter instead of freeing with the last handle.** Without destructors a notifier can't see its last copy go; std.task closes the notifiers it makes, and a program closes its own. Alternative: a notifier record owned by a reference-counted cell (an actor's), freed by the ordinary drop; it would cross tasks without copying, but it is not what D181 describes. Recommended: as built.
4. **Handles from 2^23, raw descriptors below it** in the descriptor primitives, so `io.fd_stream(fd)` and the standard streams keep working; a `File` built by hand is refused by std.fs itself. Alternative: separate primitives for handles and descriptors (more primitives, and std.io's `Pollable` split in two). Recommended: as built.

## Evidence

Reproducers of the reviews (`review1/repro/runtime/`, `review2/repro-r4/`), before (95785ab) and after:

- **H8** `b2_forged_notifier.my`: before, natively a segmentation fault (exit 139), interpreted `list index 4096 out of bounds` inside `selfhost/interp.my`; after, both `runtime error: use of a closed notifier` at `lib/std/task.my`, exit 1. Cases `forged_notifier`, `wait_after_close`, `listen_after_close`, `closed_twice`, `close_ends_the_waits` in `lib/std/task.my`.
- **M13** (`stale.my`, rewritten for D177's bytes as `STALE` in `tests/burn/test_net.py`): a stale copy's write, close, a forged stream and listener, a stale UDP send and accept are `Other(9)`, and the next connection reads only its own bytes; before, the forged `TcpStream { handle: 4 }` wrote `Ok(1)` into a live socket.
- **File and Child**: a copy of a closed `File` wrote `INJECTED` into the file opened after it (`next file: INJECTEDmine`) and `File { fd: 1 }` wrote to stdout before; after, `Other(9)` for both (cases `closing` in `lib/std/fs.my`, `stale_copies` in `lib/std/process.my`).
- **M10** (`rss.py`, 200,000 calls): reply channel per request 20.2 MB before, 11.1 MB after; `task.first` 15.6 MB, 11.2 MB.
- **M11** (`b4_timed_waiters_cliff.my`, 32,000 receivers, best of 3 on 4 workers): with `recv_timeout(60000)` 3.96 s before, 0.30 s after; without a limit 0.19 and 0.20 s.
- **M12** (`bug_stdin_deadlock.my` with D177's bytes): the blocking `write` still deadlocks interpreted and on `MYLA_THREADS=1` (timeout, exit 124), as it must; `write_async` gives `wrote 600000 read 600000` interpreted, natively and on one worker. Case `input_written_while_output_read` in `lib/std/process.my` (interpreted, where tasks take turns).
- **cwd and NUL** (`bug_bad_cwd.my`): `program not found` twice before; `working directory not found` and `invalid input` after, on both runners. Cases in `spawn_errors`, `tests.burn.test_process` (the pinned output now says `working directory 2`).
- **D180**: `LINES` in `tests/burn/test_net.py`, 20 connections echoing 50 lines each in pieces with a `"\r"` and a last line without `"\n"`: both runners, and natively on one worker. The doc block of Net.md runs.
- **S4** (`nb_async.my`, `nb.py`): natively `Err(error 11 (Other(11)))` four times before; both lines and the end after. `test_a_non_blocking_input_read_by_the_only_task` in `tests/burn/test_time.py`.
- **D184**: `checked_port`'s cases in `lib/std/net.my`.

Cost (best of n, on a machine shared with four other lanes):

- Sockets: 8 connections × 20,000 round trips of 16 bytes (`read_async` and `write_async` on each side): 4 workers 9.04 and 9.52 s before, 8.98 and 9.35 after; one worker 6.83 and 6.88 before, 6.76 and 7.00 after (within noise).
- Files: 1,000,000 unbuffered 16-byte writes and then reads of a `File`, one thread: 0.469 to 0.482 s before, 0.488 to 0.496 after (about 3 %, a lock and a look-up beside each system call).
- Notifiers: 1,000,000 `notify_one` and `wait` on one task: 0.078 s before, 0.097 after on one worker (two look-ups a round); 200,000 rounds of a wait mode 0.063 and 0.066 s.

Suites: `lib/std/task.my` 36/36, `net.my` 96/96, `process.my` 48/48, `fs.my` 73/73, `io.my` 24/24, interpreted, `--native`, `--target aarch64-linux` and `--target wasm32-wasi`; `scripts/test-target.py` aarch64-linux and wasm32-wasi for `test_net`, `test_process`, `test_time` (all pass); `tests.burn.test_net`, `test_process`, `test_time` natively; `scripts/test.sh fast`: 832 tests, the one failure `test_embedded_std` (expected until the seed commit); `scripts/test.sh` (full, with `test_std_modules`, `test_compiler_parity`, `test_lsp`, the concurrency stress tests): 1,483 tests, 336 skipped, the same one failure. The bootstrap reaches its fixed point after every commit.

## The owner's decision (2026-11-11)

The proposals stand as built (D189).
