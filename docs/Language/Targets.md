# Targets

What a Myla program can count on wherever it runs, and what depends on the target it was built for ([[MYLA-266]]). `myla build` builds for the machine it runs on unless `--target` says otherwise (D127), and `myla run` interprets on the machine itself.

| Target | `--target` | What runs it |
| --- | --- | --- |
| Linux on x86-64 | `x86_64-linux` | The machine: a static executable, no libc |
| Linux on aarch64 | `aarch64-linux` | The machine (a Raspberry Pi 4 or 5 with a 64-bit OS, an ARM server): a static executable, no libc |
| WebAssembly on WASI preview 1 | `wasm32-wasi` | A WASI host: `node tools/wasm/run.mjs`, wasmtime, or a web page through `tools/wasm/myla.mjs` (D125) |

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
| Child processes (`std.process.run`, `spawn`) | Yes | Yes | No: `Err(SpawnError.Unsupported)` |
| Workers for tasks | `MYLA_THREADS`, else one per CPU the process may use; at most 32 | The same | One; `MYLA_THREADS` is ignored (D125 (4)) |
| Input that suspends a task (`read_line_async`, …) | Yes: the task waits, the others run | Yes | No: the read blocks the program (the host can't wait for input without blocking) |
| `task.sleep`, `task.timeout` | Yes | Yes | Yes (`poll_oneoff`) |
| Files and directories | The whole file system | The whole file system | What the host shares: the first preopened directory; mode bits are made up from the file's kind |
| The working directory | The process's (`getcwd`) | The process's | `PWD` from the environment |
| `exit(code)` | The low 8 bits reach the parent (POSIX) | The same | The host's `proc_exit`; `run.mjs` passes the code on |
| A child's end by a signal (`ExitStatus.Signaled`) | Yes | Yes | No processes |
| The main thread's stack | Up to 120 MiB (the soft limit raised, MYLA-182) | The same (under qemu-user: 8 MiB unless `QEMU_STACK_SIZE` says more) | 8 MiB of shadow stack, and the engine's own call stack (Node: `--stack-size`) |
| A worker's stack | 8 MiB, with a guard page | The same | One worker: the main stack |
| Memory | The machine's | The machine's | At most 4 GiB, which the program never gives back |
| A line printed whole while other workers print | Up to `PIPE_BUF` (4 KiB) per line | The same | One worker: always |
| Debug information (`myla build -g`) | Yes ([[Development/Debugging]]) | Not yet ([[MYLA-259]]) | Not yet |

## How each target is built

An implementation may leave out what only parallel workers need when only one worker can exist: the deep copies at task boundaries and the atomic counts of actor handles (D133). Values are immutable, so the difference shows only in speed. The details of each target's code generation, runtime and platform layer are on [[Architecture/Native-backend]].
