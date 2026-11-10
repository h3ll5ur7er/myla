---
id: MYLA-336
title: "New platform primitives: entropy, file descriptors, pipes"
type: feature
status: done
priority: medium
labels: [platforms, primitives, stdlib, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]]. One task for every primitive that waves 3 and 4 need (sockets, terminals and signals excepted), so the platform layer and the seed's staging commit (D156) change once rather than in three lanes. It belongs to the platform track and runs alone.

- **Owns:** `lib/std/platform.my`, `lib/std/platform_aarch64.my`, `lib/std/platform_wasm.my`, `selfhost/` (the primitive tables, the interpreter, the three backends)
- **Needs:** nothing; it can start as soon as its wave does

- [x] Entropy: `__random_bytes(n)` (`getrandom`; WASI `random_get`)
- [x] File descriptors: open with flags and a mode, read and write at the cursor, seek, close, fstat (size, mode, modification time); the `IoError` causes as today
- [x] Pipes and children: spawn with pipes for stdin, stdout and stderr; read and write them; wait; kill. On wasm32 `Unsupported`
- [x] Each on x86-64, aarch64 and wasm32 and in the interpreter; the per-target suites ([[MYLA-268]]) run them
- [x] [[Language/Targets]] updated with the new capabilities

## Done (2026-11-07)

Six new primitives, each a function of `std.rt` (`__open` is `std.rt.open`) over `std.platform`, and in the interpreter the host's own; reading, writing and closing a descriptor are the existing `__read`, `__write` and `__close`, waiting and signalling the existing `__reap` and `__kill`. The tables are on [[Language/Standard-library/Fs#descriptor-and-entropy-primitives]] and [[Language/Standard-library/Process#process-primitives]].

| Primitive | x86-64 | aarch64 | wasm32 |
| --- | --- | --- | --- |
| `__random_bytes(n: int) -> [uint8]` | getrandom(2) until `n` bytes | the same (278) | `random_get`, 64 KB a call |
| `__open(path: str, flags: int, mode: int) -> int` (flags: 1 read, 2 write, 4 create, 8 truncate, 16 append, 32 exclusive) | open(2), `O_CLOEXEC` | openat(2) | `path_open`: oflags, rights to read or write, `FDFLAGS_APPEND`; no permissions |
| `__seek(fd: int, offset: int64, whence: int) -> int64` | lseek(2) | lseek(2) | `fd_seek` |
| `__fstat(fd: int) -> [int64]` (`[size, mode, mtime_ns]`) | fstat(2) | fstat(2), the generic `struct stat` | `fd_filestat_get`, the mode from the kind |
| `__spawn_piped(program: str, argv: [str], opts: [str]) -> [int]` (`[errno, pid, in, out, err, exited]`) | fork, exec, four `pipe2`, a pidfd | `clone` for the fork | `[38, 0, -1, -1, -1, -1]` |
| `__try_reap(pid: int) -> int` (256 while it runs) | wait4(2), `WNOHANG` | the same | 256 with ENOSYS |

`__kill` now records its errno (ESRCH; ENOSYS on wasm32). `std.platform`'s `spawn_with` and `spawn_piped` share `start_child`, which also closes the pipes it made when the fork fails (they leaked before). The WASI imports `random_get` and `fd_seek` are numbers 19 and 20, `memory.grow` 21 (`selfhost/runtime_wasm.my`); the Node shim (`tools/wasm/wasi.mjs`, `node_fs.mjs`, `mem_fs.mjs`) gained both, the access rights and `FDFLAGS_APPEND` of `path_open`, and a cursor per handle (Node has no lseek).

No seed staging: the seed compiles only the compiler, whose `std.rt` and `std.platform` use no new primitive or runtime variable; only the interpreter (`selfhost/interp.my`, built by stage 3) and the tests call the new ones. `scripts/bootstrap.sh` from the unchanged seed reaches the fixed point. A lane of wave 3 that calls one from a module the compiler imports (`std.fs`, `std.process`, `std.io`) needs a seed that knows it: this task's pull request's seed commit.

## Evidence

- Test first: `tests/burn/test_platform_primitives.py` failed before the primitives existed (10 failures, 4 errors: "unknown function '__open'" and the like); after, all pass natively against the interpreter (7 tests, the wasm32-only one skipped), under `scripts/test-target.py aarch64-linux` (qemu) and `wasm32-wasi` (Node; the pipes and the mode bits excused in `_targets.py`, `PipesOnWasm` checking ENOSYS instead). It covers entropy (lengths, 256 byte values seen in 100,000, a negative `n`), every open flag and error (EEXIST, ENOENT, EISDIR, EINVAL for a NUL, no access or an unknown bit), reads, writes and seeks at the cursor, appending, EBADF on a read-only or closed descriptor, ESPIPE, `__fstat`'s three values and a 0600 mode, a child's three pipes through `cat` and `sh` (an exit status, stderr, `try_reap` while running and after, a kill by SIGTERM, ECHILD, ESRCH, a directory and environment, EPIPE after it ended, a program that isn't there), and each primitive's warning outside `std` and its silencing by `#allow` (D100, D161).
- `test_fs`, `test_stdio`, `test_process`: pass natively and on both targets. `test_wasm` (35 tests, 8 skipped as before) and `test_aarch64` (20, 1 skipped) pass. `scripts/test.sh fast`: 607 tests, OK.
- `myla test` on `lib/std/platform.my`, `platform_aarch64.my`, `platform_wasm.my`, `rt.my` and `selfhost/runtime_wasm.my` passes (the new `linux_open_flags`, `exit_of`, `mode_of_type`, `open_rights` and `is_platform_primitive` cases among them).
- `scripts/bootstrap.sh`: byte-identical fixed point (9,963,251 bytes), from the unchanged seed.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-426]]: wasm32 maps unknown errnos to EIO.
