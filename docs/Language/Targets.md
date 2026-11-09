# Targets

What a Myla program can count on wherever it runs, and what depends on the target it was built for ([[MYLA-266]]). `myla build` builds for the machine it runs on unless `--target` says otherwise (D127), and `myla run` interprets on the machine itself.

| Target | `--target` | What runs it |
| --- | --- | --- |
| Linux on x86-64 | `x86_64-linux` | The machine: a static executable, no libc |
| Linux on aarch64 | `aarch64-linux` | The machine (a Raspberry Pi 4 or 5 with a 64-bit OS, an ARM server): a static executable, no libc |
| WebAssembly on WASI preview 1 | `wasm32-wasi` | Node: `node tools/wasm/run.mjs`, or a web page through `tools/wasm/myla.mjs` (D125). Node is the host the suites test (D158); another WASI preview 1 host such as wasmtime should run the programs too, but nothing checks it |

[TOC]

## The same on every target

The language means the same everywhere, and the interpreter and every target print the same for a program that doesn't depend on what this page lists as differing:

- **Integers** wrap at their width; `MIN / -1` is `MIN` and `MIN % -1` is 0; shift amounts are masked at run time ([[Language/Expressions-and-operators]]).
- **Floats** follow IEEE 754 and print the same digits everywhere: the formatting is Myla code (`std.num`). A NaN prints as `nan`. Its sign and payload, which processors set differently, can't be seen: `std.math.to_bits` reads every NaN as `0x7FF8000000000000`, and `copysign` reads a NaN's sign as positive (D128).
- **`std.math`** gives bit-identical results everywhere: its functions are Myla code over the processor's correctly rounded `sqrt`.
- **Maps** iterate in insertion order (D105).
- **Runtime errors** print `runtime error: <message>` and the position, and exit with status 1 ([[Language/Attributes-and-testing]]). Running out of the stack is `runtime error: stack overflow` with status 1 on every target, without a position (MYLA-182, [[MYLA-261]]).
- **`become`** passes six argument words freely on every target, and on the stack no more than the function received (D131, [[Language/Statements]]).
- **The order of tasks** on one worker is the defined order of D110. On several workers it is whatever the timing makes it; a program whose output depends on it is wrong.
- **Errors** are the same causes everywhere: `IoError` and `SpawnError` name `NotFound`, `PermissionDenied`, `AlreadyExists`, `IsADirectory` and the rest (D129, [[Language/Standard-library]]). Only `Other(code)` carries a platform's own number, which isn't portable.

## What a target can do

A program learns that its target lacks something from an error: the cause `Unsupported` (D129, D132). Code chosen per target at compile time, for the standard library and packages, is still to come ([[MYLA-245]]).

| | x86-64 Linux | aarch64 Linux | wasm32 on WASI |
| --- | --- | --- | --- |
| Child processes (`std.process.run`, `run_async`, `command`) | Yes | Yes | No: `Err(SpawnError.Unsupported)` |
| A child with pipes for its stdin, stdout and stderr, waited for or not, signalled (the primitives `__spawn_piped`, `__try_reap`, `__kill`, [[MYLA-336]]); each stream instead this process's or nothing, and the input a descriptor handed over ([[MYLA-378]]) | Yes: fork, exec, pipes, a pidfd, `wait4`; `/dev/null`, `dup2` | Yes: `clone` for the fork, `dup3` | No: ENOSYS, the errno of `Unsupported` |
| Files opened with flags, read and written at a cursor, seeked, their size, mode and modification time, closed with the close's errno (`__open`, `__seek`, `__fstat`, `__close`, [[MYLA-336]], [[MYLA-378]]) | Yes | Yes (`openat`) | Yes, within what the host shares (`path_open`, `fd_seek`, `fd_filestat_get`, `fd_close`); the mode given to a new file isn't used, and the mode read is made up from its kind |
| A path's size, mode, time, device and number without opening it, a symbolic link followed or itself (`__path_stat`, [[MYLA-378]], [[MYLA-363]]) | `stat`, `lstat` | `newfstatat`, with `AT_SYMLINK_NOFOLLOW` for a link itself | `path_filestat_get` with the follow flag or without; the mode made up from the kind (a link 0o120777) |
| A string's bytes as a list and back in one copy, a builder's capacity (`__str_to_bytes`, `__bytes_to_str`, `StringBuilder(n)`, [[MYLA-369]]) | Yes | Yes | Yes (std.rt's, in Myla) |
| Sockets: TCP, UDP, name lookup (`std.net`, the `__sock_*` primitives, [[MYLA-346]]) | Yes: the BSD socket calls, epoll for the reactor | Yes (the same calls; under qemu-user too) | No: `Unsupported` (WASI preview 1 has no sockets) |
| The terminal: whether a stream is one, its size, raw mode, escape sequences (`std.term`, the `__term_*` primitives, [[MYLA-350]]) | Yes: `ioctl` (TCGETS, TCSETS, TIOCGWINSZ) | Yes (the same; under qemu-user too) | No: nothing is a terminal, the size is `None`, raw mode `Unsupported` |
| SIGINT and SIGTERM awaited (`std.signal`, `__signal_listen`, `__signal_take`, [[MYLA-350]]) | Yes: a handler writes them to a self-pipe the reactor waits on | Yes | No: `Unsupported` (WASI has no signals) |
| The system's entropy (`__random_bytes`, [[MYLA-336]]) | `getrandom` | `getrandom` | The host's `random_get` (Node: `crypto.getRandomValues`) |
| The wall clock (`__wall_ns`, `std.time.now_utc`, [[MYLA-334]]) | `clock_gettime(CLOCK_REALTIME)` | The same | `clock_time_get` with the realtime clock (Node: `Date.now()`, so milliseconds) |
| Workers for tasks | `MYLA_THREADS`, else one per CPU the process may use; at most 32 | The same | One; `MYLA_THREADS` is ignored (D125 (4)) |
| Input that suspends a task (`read_line_async`, …) | Yes: the task waits, the others run | Yes | No: the read blocks the program (the host can't wait for input without blocking) |
| `task.sleep`, `task.timeout` | Yes | Yes | Yes (`poll_oneoff`) |
| Files and directories | The whole file system | The whole file system | What the host shares: the first preopened directory; mode bits are made up from the file's kind |
| The working directory | The process's (`getcwd`) | The process's | `PWD` from the environment |
| `exit(code)` | The low 8 bits reach the parent (POSIX) | The same | The host's `proc_exit`; `run.mjs` passes the code on |
| A child's end by a signal (`ExitStatus.Signaled`) | Yes | Yes | No processes |
| The main thread's stack | Up to 120 MiB (the soft limit raised, MYLA-182) | The same (under qemu-user: 8 MiB unless `QEMU_STACK_SIZE` says more) | 8 MiB of shadow stack, and the engine's own call stack (Node: `--stack-size`) |
| A worker's stack | 8 MiB, with a guard page | The same | One worker: the main stack |
| Memory | The machine's; a freed cell bigger than 16 MiB goes back to the system (D157) | The machine's, as on x86-64 | At most 4 GiB, which the program never gives back: a freed big cell is reused by a later one it is large enough for, and a growing list or string at the top of the memory grows where it is (a list of 150 million `int64`s fits, [[MYLA-284]]) |
| A line printed whole while other workers print | Up to `PIPE_BUF` (4 KiB) per line | The same | One worker: always |
| Debug information (`myla build -g`) | Yes ([[Development/Debugging]]) | Not yet ([[MYLA-259]]) | Not yet |

## Sockets on another system

`std.net` never sees a file descriptor or a `sockaddr` ([[Language/Standard-library/Net#porting-sockets-to-another-system]]). A port, Windows' over Winsock next, gives `std.platform`'s socket functions again (`sock_open` to `sock_close`, `sock_poll`, `net_config`, and the poller's `poller_watch_socket` and `poller_forget_socket`): each gives 0 or more or minus an errno, its codes mapped onto Linux's numbers (`WSAECONNREFUSED` onto ECONNREFUSED, `WSAEWOULDBLOCK` onto EAGAIN, or EINPROGRESS for a connect); addresses cross as a portable record; a socket starts blocking and is made non-blocking explicitly; data is sent and received, never read or written, and a socket has its own close. Readiness is 1 to receive or accept, 2 to send or a connect's end, an error or a hang-up both: `WSAPoll` for `sock_poll`, and for the reactor `WSAPoll` beside its wake-up event or IOCP. The hosts file's path and the name servers come from `net_config`, as Windows keeps both elsewhere.

## The terminal and signals on another system

`std.term` and `std.signal` never see an `ioctl`, a termios byte or a signal number beyond 2 and 15 ([[Language/Standard-library/Term#porting-to-another-system]], [[Language/Standard-library/Signal#porting-to-another-system]]). A port, Windows' over the console API next, gives `std.platform`'s `term_is_tty`, `term_size`, `term_get_mode`, `term_set_mode`, `term_make_raw`, `term_enable_vt`, `signal_listen` and `signal_take` again, each 0 or more or minus an errno (ENOTTY for a stream that isn't a terminal). The descriptors 0 to 2 name the standard streams (`GetStdHandle`); being a terminal is `GetConsoleMode` succeeding; the size is the visible window of `GetConsoleScreenBufferInfo`, as columns times 65536 plus rows; a mode is an opaque block the port fills (the console mode) and gets back unread; raw mode clears line input, echo and processed input and sets `ENABLE_VIRTUAL_TERMINAL_INPUT`, so keys arrive as the escape sequences `parse_key` reads; `term_enable_vt` sets `ENABLE_VIRTUAL_TERMINAL_PROCESSING`. A signal comes through a handle the reactor waits on as on input, one byte each, 2 for an interrupt and 15 for termination: a `SetConsoleCtrlHandler` routine writes `CTRL_C_EVENT` and `CTRL_BREAK_EVENT` as 2 and `CTRL_CLOSE_EVENT`, `CTRL_LOGOFF_EVENT` and `CTRL_SHUTDOWN_EVENT` as 15 to a pipe, and nothing is installed until a program listens.

## Files and children on another system

`std.fs` and `std.process` see no `struct stat`, file descriptor table or `fork` ([[MYLA-378]], [[MYLA-363]]). A port, Windows' next, gives `std.platform`'s `path_stat(path, follow, out)` again: five words at `out`, the size, a mode in Linux's bits (the type bits 0o100000, 0o40000, 0o120000 for a regular file, a directory, a link, made up from the attributes as wasm32 makes them up from WASI's file type; the permission bits from the read-only attribute, say), the modification time in nanoseconds since 1970, and a device and a file number that together name one file (the volume's serial number and the file index of `GetFileInformationByHandle`), a link followed or not (`FILE_FLAG_OPEN_REPARSE_POINT`); 0 or minus an errno, mapped onto Linux's numbers. Its `close(fd)` gives the close's result as one (`CloseHandle`). Its `spawn_piped(paths, argv, opts)` reads the three streams as `opts[1]`'s letters (`std.rt.spawn_piped`): `p` a pipe whose other end comes back in the result, `i` this process's, `n` the `NUL` device, and for the input `t` a text or `d` a descriptor handed over, which a `CreateProcess` takes as the handles of `STARTUPINFO`; a stream that isn't a pipe is -1 in the result, the rest as Linux's (`[errno, pid, in, out, err, exited]`, `exited` a handle the reactor waits on). The string and builder primitives of [[MYLA-369]] are std.rt's own Myla and need nothing of a port.

## How each target is built

Every target runs the burn suites that build and run programs, x86-64 natively and the others under qemu-aarch64 and Node (`scripts/test-target.py`, [[Development/Testing]], [[MYLA-268]]); `myla test --target <t>` runs a file's or a project's own `#test` cases there the same way ([[Language/Attributes-and-testing#native-runs]], D162). What the others are excused from, and why, is in `tests/burn/_targets.py`: only what the table above lists (no processes on wasm32, one worker, Node's own memory measured), the tests that read x86-64 code, and the standard library's own cases under qemu-aarch64 (a qemu process per case: `std.int`'s 1826 take 4.6 minutes); on wasm32 they run, every case ([[MYLA-370]]).

An implementation may leave out what only parallel workers need when only one worker can exist: the deep copies at task boundaries and the atomic counts of actor handles (D133). Values are immutable, so the difference shows only in speed. wasm32 leaves out both: a value crossing between tasks keeps its counts (an argument of a child, a capture of an async lambda, a result), and an actor handle's count is a plain one. A program handing a 20000-element list and a 200-entry map to 6000 children ran in 0.42 to 0.55 s instead of 0.62 to 0.69 s under Node (2026-11-05). The details of each target's code generation, runtime and platform layer are on [[Architecture/Native-backend]].
