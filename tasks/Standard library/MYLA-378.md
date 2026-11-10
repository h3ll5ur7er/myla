---
id: MYLA-378
title: "Platform primitives for wave 3's gaps: a path's stat, a child's stdout and stderr, a descriptor as stdin"
type: feature
status: done
priority: low
labels: [platforms, primitives, stdlib]
---
Found by the file and process lanes ([[MYLA-339]], [[MYLA-340]]). Each is a primitive on x86-64, aarch64 and wasm32 and in the interpreter, and a seed staging (D156).

- [x] `__stat(path) -> [size, mode, mtime_ns]`, so `fs.metadata(path)` doesn't open the file (today a file the program can't read is `PermissionDenied`, and a device, FIFO or socket gets size 0 and time 0). With `lstat`'s form, [[MYLA-363]]
- [x] Spawning with stdout and stderr inherited or null, not only piped: then `Command.stdout_from` and `stderr_from`, and a child that writes more than 64 KiB to a stream nobody reads no longer stops
- [x] A descriptor as a child's stdin, so a `Pipeline` joins its two children directly instead of the parent copying (which a consumer that writes much more than it reads can still stall)
- [x] `__close` records its errno, so `File.close()` reports EIO and doesn't need an `__fstat` first

## What was built

- **`__path_stat(path: str, follow: bool) -> [int64]`**, `[size, mode, mtime, dev, ino]` or `[]` with the errno: a new name, as `__stat(path) -> int` stays (`exists`, `is_dir`, `is_file`) and the seed knows it with its old type. One primitive with a flag rather than `__stat`/`__lstat`, as WASI's `path_filestat_get` and Windows' `CreateFile` (with or without `FILE_FLAG_OPEN_REPARSE_POINT`) both take one. The device and file number are there so a walk can tell a loop ([[MYLA-363]]). `std.platform.path_stat(path, follow, out)` on each target: x86-64 `stat`/`lstat`, aarch64 `newfstatat` with or without `AT_SYMLINK_NOFOLLOW`, wasm32 `path_filestat_get` with or without `LOOKUPFLAGS_SYMLINK_FOLLOW` (a new `on_path_lookup`; `mode_of_type` makes up 0o120777 for a link). `fs.metadata` uses it.
- **`__close`'s errno**: `std.platform.close` gives the result on every target (wasm32 `fd_close`'s), `std.rt.close` records it: EBADF for a descriptor that isn't open (a negative one too), EIO; EINTR counts as closed (Linux has closed it then, and closing again could close another file's). `File.close()` reads it, without an `__fstat` first. The primitive's type didn't change, so it needed no staging.
- **A child's streams** (no new primitive, so no staging either): `__spawn_piped`'s `opts[1]` may be three letters for stdin, stdout and stderr, `p` a pipe, `i` this process's, `n` nothing (/dev/null), and for stdin `t` the text `opts[2]` or `d` the descriptor whose number `opts[2]` is, handed over (closed in the parent once the child has it; one that isn't open is EBADF before the fork, as the child's `dup2` would fail unseen). `exec_child` now `dup2`s the three descriptors it is given (`F_SETFD` for one already in place) and every descriptor the parent makes is `O_CLOEXEC`, `run_with`'s two pipes too, so the child closes nothing by hand. A stream that isn't a pipe is -1 in the result. x86-64's processes section and aarch64's are the same text with aarch64's calls (`dup3`, `clone`, `ppoll`, `wait4`'s five words).
- **std.process**: `Command.stdout_from(how)`, `stderr_from(how)` (`output` and `output_async` take them too, through `spawn` and `wait_with_output`), `stdin_from_stdout(out: ChildStdout)`; `spawn` always goes through `__spawn_piped` with the letters (`stdio_letters`). A `Pipeline` spawns the second with the first's output as its input and only collects the second's output and both errors (`Collected`, which replaces the copying `Pump`).

## Proposal (open decision)

`Command.stdin_from_stdout(out: ChildStdout)` names the one descriptor a command can take as its input for now. Alternatives: a variant `Stdio.From(ChildStdout)` (Rust's `Stdio::from(child_stdout)`), which changes a public enum that programs may match exhaustively; or a general `stdin_from_fd(fd)`, which hands a program the descriptors it shouldn't see. I recommend the method as built: it keeps `Stdio` as it is, and a `File` as input can come later the same way (`stdin_from_file`).

## Evidence

- Before: the seed compiler (eaa905d's) rejects a program calling `__path_stat`: `type error: unknown function '__path_stat'`. After: `tests/burn/test_platform_primitives.py`'s `Paths` (a file, a link followed and not, a dangling link, a directory, the device and number, ENOENT, EINVAL, `__close` twice and of -1: `0`, `9`, `9`) passes interpreted and natively, on aarch64 (qemu) and wasm32 (Node): `scripts/test-target.py aarch64-linux|wasm32-wasi tests.burn.test_platform_primitives` OK. `Warnings` holds `__path_stat` to the primitive warning and its arguments to `(path: str, follow: bool)`.
- `tests/burn/test_fs.py`'s `test_symbolic_links` (metadata of a link, a dangling link `NotFound`, a mode-0 file's metadata without opening it), natively and on both targets.
- `File.close`: `fs.my`'s `closing` (a second close and a copy's close `Other(9)`) passes interpreted and natively; it now reads `__close`'s errno.
- A pipeline whose second child writes 1 MB before it reads its input (`head -c 200000 /dev/zero | sh -c "head -c 1000000 /dev/zero; wc -c"`, `process.my`'s `pipeline_second_writes_first`): with eaa905d's std.process, natively, the test hangs (killed by a 30 s timeout); now it passes interpreted (4.3 s), natively, on aarch64 and wasm32 (`Unsupported` there). `output_modes`: 1 MB to a `Null` output nobody reads ends by itself (`try_wait` only), `Null` and `Inherit` streams aren't pipes, `output` with a `Null` output gives an empty `stdout` and the error. `input_from_a_child`: `printf abc` into `tr a-z A-Z` gives `ABC`; the handed-over stream is closed here, and handing it over again is `SpawnError.Other(9)`. `build/myla test lib/std/process.my --stdlib lib`: 34/34 interpreted, `--native`, `--target aarch64-linux` and `--target wasm32-wasi`.
- Measured natively (2026-11-09, a machine other lanes were using): 256 MiB of `head -c` through `pipe(command("wc").arg("-c"))` took 918 to 2,187 ms with the copy, 109 to 127 ms joined (a shell's own pipe 117 to 148 ms).
- [[MYLA-397]] (a platform module can't be tested on its own target): each platform module's own cases (`stdio_mode`, `descriptor_of`, `mode_of_type`) ran interpreted and `--native` on x86-64 (`platform.my` 23/23, `platform_aarch64.my` 23/23, `platform_wasm.my` 13/13); their primitives ran on their own targets through the burn programs above and `std.process`'s and `std.fs`'s cases.
- The suites: see [[MYLA-369]]'s evidence, run once for the three tasks.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-419]]: a bad `cwd` reports "program not found"; its API proposal is D185.
