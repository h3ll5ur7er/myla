---
id: MYLA-701
title: "Windows step 2: the platform interface in Myla's terms"
type: feature
status: done
priority: high
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). D209, the part of [[MYLA-265]] the port needs before it starts: Windows would otherwise translate its API into Linux shapes, as wasm32 does today.

- [x] Errors as Myla's causes (D129) from the platform functions, not negative Linux errnos
- [x] A directory's entries as names and kinds, not `getdents64` records
- [x] A file's kind and size, not `st_mode` bits
- [x] The poller and processes as operations a target may lack (`Unsupported`, D129): processes and sockets declared (`PROCESSES`, `SOCKETS`) and `UNSUPPORTED` without them; the poller's reshaping is [[MYLA-716]] (wasm32's is an implementation on `poll_oneoff`, not a translation, so it stays)
- [x] std.rt, std.fs, std.process, std.io, std.net and the interpreter's primitives adapted; wasm32's translation layer removed where the new shapes make it needless
- [x] A test that every platform module offers the same functions with the same types

## What changed

**The interface (D209).** Every function of the three platform modules gives a result or minus a *cause code*, never a system's number. The codes are std.ioerror's (`NOT_FOUND` 1 … `INVALID_DATA` 21 in `IoError`'s order; `WOULD_BLOCK` 32, `IN_PROGRESS` 33, `BAD_HANDLE` 34, `NOT_A_TERMINAL` 35, which std.rt and std.net act on; `OTHER` 256 plus the system's own code), declared again as `int64` constants of each platform module. The Linux modules map errnos in `cause` (their system calls go through `sys`/`sys5`); wasm32 maps WASI's through Linux's numbers (`cause(errno_linux(e))`), so an `Other` reads as before on every target ([[MYLA-426]]). A file is its kind (`KIND_FILE` … `KIND_OTHER`, `KIND_UNKNOWN` for an untyped entry), size, permission bits and time: `path_kind` replaces `mode_of`; `fd_stat` gives four words, `path_stat` six. A directory's entries are names and kinds: `dir_read` fills records of the module's own (getdents64's on Linux, WASI's own on wasm32, no longer rewritten), which `dir_entry_size`, `dir_entry_name`, `dir_entry_name_len` and `dir_entry_kind` read. What a target lacks is a constant (`PROCESSES`, `SOCKETS`; false on wasm32) and the cause `UNSUPPORTED`.

**Above it.** std.rt records the platform's cause (`record` is unchanged) and sets causes of its own (`os.INVALID_INPUT`, `os.BAD_HANDLE`, `os.NOT_FOUND`), and its `errno_text` reads causes. std.ioerror gains the cause codes, `from_cause` and `code_number` (the number an error type's `Other` shows for a cause it has no variant for: Linux's errno, as before, so `Other(9)`, `terminal error 22`, `SpawnError.WorkingDir(2)` stay); `from_errno` stays for programs holding a Linux errno, and nothing in std calls it. std.fs, std.io, std.process, std.net, std.http, std.term and std.signal read causes (`from_cause`, the codes by name); std.fs and std.glob read kinds, not `st_mode` bits. std.path reads no modes. The interpreter's primitives forward to the CLI's own std.rt, so they needed no change: their results change meaning with the library (`__io_errno` a cause code, `__stat` a kind, `__fstat`'s and `__path_stat`'s new words). No primitive changed its name or type, so the seed bootstraps the sources as they are: **no `Stage:` commit**.

## Proposal: what stays of a file's mode (std.fs), accepted 2026-11-15 as D218

`Metadata.permissions: int32` stays POSIX's permission bits (`0o7777`) on every target, each platform module giving its system's own as such bits: Linux the real ones; wasm32, which has none, made up from the kind (0o644 a file, 0o755 a directory, 0o777 a link: what it gave before); Windows from `FILE_ATTRIBUTE_READONLY` (0o444 or 0o666 for a file, 0o555 or 0o777 for a directory). The `mode` given to `make_dir` and `OpenOptions.mode` is used where the system has bits and ignored where it hasn't (wasm32 now, Windows). The type bits are gone from every interface: a kind is `FileKind`. Alternatives: Rust's portable `readonly: bool` in place of the bits (programs that read `permissions` break), or `permissions: Option<int32>`, `None` where the system has none (the same, and wasm32's made-up bits go). A `readonly()` method on `Metadata` can come beside the bits later without breaking anything. Proposed decision row: *"A file's permissions stay POSIX's bits on every target (D209): a platform without them gives what its system has as bits (wasm32 from the kind, Windows from the read-only attribute) and ignores the mode given."*

## Proposal: the cause numbering, accepted 2026-11-15 as D219

The cause codes are a numbering of their own (1 to 21 `IoError`'s order, 32 to 35 std's own, 256 on a system's own code), not Linux's errnos, so that a Windows code (`ERROR_FILE_NOT_FOUND` is 2) can't be read as a cause. The causes an error type has no variant for (`Other(9)` a closed handle, `TermError.Other(22)`, `SpawnError.WorkingDir(13)`) keep Linux's numbers on every target, the same output as before; [[MYLA-716]] has whether they become causes of their own. Alternatives: the numbering *be* Linux's errnos for the causes (then `from_errno` and `from_cause` are one function, but an unmapped Windows code collides with a Linux number), or platform functions return `Result<int64, IoError>` (an enum per system call on the hot paths, and std.platform would import std.ioerror into every program). Proposed decision row: *"The platform's errors are std.ioerror's cause codes (D209): 1 to 21 IoError's causes, 32 to 35 std's own, 256 plus a system's own code; an error type's `Other` shows Linux's errno for a cause it has no variant for, on every target."*

## Evidence

At `dab0f05` with this branch's test, `tests/burn/test_platform_interface.py`'s declarations fail, 4 of 4: x86-64's module has `EINTR`, `EAGAIN`, `EPIPE` and no cause codes or kinds; wasm32's lacks `linux_open_flags`, which both Linux modules exported (now private: it is theirs); std.ioerror has no numbering to compare. On this branch all 7 pass, on x86-64, aarch64 (qemu) and wasm32 (Node): the declarations, every function bound to a variable of its type and built for each target, and a probe calling the platform directly (`NotFound`, `AlreadyExists`, `NotEmpty`, `NotADirectory`, `Other(9)` from the functions; kinds 1 and 2; `sub/`'s entries `deeper 2` and `g.txt 1` through `dir_entry_*`; `PROCESSES` and `UNSUPPORTED` on wasm32).

The same output as before, on every runner (2026-11-14, this branch):
- `python3 -m unittest` of `test_std_modules` (interpreted and native), `test_compiler_parity`, `test_error_corpus`, `test_lazy_std`, `test_embedded_std`, `test_fs`, `test_process`, `test_stdio`, `test_term`, `test_net`, `test_platform_primitives`, `test_platform_interface`, `test_wasm`, `test_aarch64`, `test_test_native`, `test_http`: 881 tests, OK (13 skipped). `test_doc_blocks`, `test_lsp`, `test_examples_run`, `test_project_commands`: OK.
- `scripts/test-target.py aarch64-linux` with `test_fs`, `test_process`, `test_platform_primitives`, `test_platform_interface`, `test_net`, `test_term`, `test_stdio`, `test_compiler_parity`, `test_error_corpus`: 9 of 9 suites passed.
- `scripts/test-target.py wasm32-wasi` with those and `test_std_modules`: 10 of 10 passed.
- `build/myla test lib/std/<m>.my --stdlib lib` for ioerror, fs, io, glob, process, net, term, signal, rt, platform, http: all pass interpreted and `--native`; ioerror, io, fs, glob, process, net, term, signal and platform_aarch64 with `--target aarch64-linux`; platform_wasm, fs, glob, io with `--target wasm32-wasi`.
- What changed on purpose is what the primitives give, which programs don't see: `test_platform_primitives`, `test_term`'s and `test_net`'s primitive tests pin the cause codes (`-1 1` where `-1 2` was, kinds 1, 2, 3 where 32768, 16384, 40960 were, `__fstat`'s four words and `__path_stat`'s six).
- `scripts/bootstrap.sh` from the committed seed: byte-identical fixpoint (27,995,236 bytes); no primitive changed its name or type, so no seed was staged.
- `scripts/test.sh` (all): 1,708 tests, OK (366 skipped). `scripts/check-seed.sh`: the seed bootstraps these sources, the embedded library is current.

Signed off by [[Project/Review-2026-11-17]] (done).
