---
id: MYLA-339
title: File streams and temporary files
type: feature
status: done
priority: medium
labels: [stdlib, fs, streams, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #42, #45. Files bigger than memory.

- **Owns:** `lib/std/fs.my`, `docs/Language/Standard-library/Fs.md`
- **Needs:** [[MYLA-336]], [[MYLA-338]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `File` (`open` with modes, `create`, `append`) implementing `Read`, `Write` and `Seek`; `len`, `flush`, `close`, closing when it goes out of scope if the language allows, else explicit
- [x] `metadata(path)`: size, kind, permissions, modification time
- [x] Temporary files and directories under `$TMPDIR`; `std.test.temp_dir` built on them
- [x] A 4 GB file copied with a 1 MB buffer on x86-64 in constant memory
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Done (2026-11-08)

`File`, `OpenOptions`, `Metadata`, `FileKind` and the temporary files and directories are in `std.fs` ([[Language/Standard-library/Fs#files]]). `std.io` imports `IoError` and `from_errno` from `std.fs`, and `std.fs` now imports `Read`, `Write`, `Seek`, `SeekFrom` and `Pollable` from `std.io`: Myla accepts the cycle (two modules importing each other's types and functions build and run, interpreted and natively), so neither module's names moved and `lib/std/io.my` is unchanged.

- **Names:** `open(path)`, `create(path)`, `open_append(path)` (`append` is a built-in name, which no declaration may reuse), `options()` and its methods `read`, `write`, `append`, `truncate`, `create`, `create_new`, `mode` and `open`; on a `File` `read`, `read_str`, `write`, `write_str`, `flush`, `seek`, `len`, `metadata`, `close`, `descriptor`; `metadata(path)`; `temp_root()`, `make_temp_dir()`, `make_temp_dir_in(dir, prefix)`, `make_temp_file()`, `make_temp_file_in(dir, prefix)`.
- **Closing is explicit:** Myla has no destructors (no drop on user types in [[Language/Types]] or the decisions), so `defer { let closed = f.close() }` is the idiom. A copy shares the descriptor; after `close` the file, and a copy of it, fail with `Other(9)` (EBADF), a second `close` too, until the platform reuses the number. `__close` reports nothing, so `close` asks `__fstat` first.
- **`metadata(path)`** opens a file or directory to read it (`__fstat` is the only primitive with a size and a time), so a file the program can't read is `PermissionDenied`; a device, FIFO or socket isn't opened, and gets size and time 0. A primitive `__stat` with all three values would lift both.
- **Temporary names:** a prefix and 16 hex digits of `__random_bytes(8)`, made by mkdir (0700) or `O_EXCL` open (0600), a taken name tried again up to 100 times. `std.test.temp_dir()` is `make_temp_dir_in(root, "d")` in the case's root (the root made first, as before), and `std.test.temp_file()` is new.

## Evidence

- Test first: the test functions failed before the code (`unknown function 'make_temp_dir'`), `std.test`'s `temp_dirs_and_files` too (`unknown function 'temp_file'`).
- `myla test lib/std/fs.my --stdlib lib`: 57/57 (49 new: 8 test functions, 41 cases), the same report with `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node). `lib/std/test.my`: 31/31 on all four; on wasm32 the harness runs the cases in itself, where there is no case root (`temp_dir` there was a runtime error before this task too), so the new test function returns at once. `lib/std/io.my` 24/24, `path`, `slice`, `process` unchanged, interpreted and native alike.
- `python3 -m unittest tests.burn.test_fs tests.burn.test_stdio tests.burn.test_test_functions`: 38 OK (the last pinned `temp_dir`'s old name `d0`; it now checks `d` and 16 hex digits); `scripts/test-target.py aarch64-linux` and `wasm32-wasi` with `test_fs` and `test_stdio`: OK. After a bootstrap (fixed point, 13,914,872 bytes; 13,789,685 before, as the compiler links `std.fs`), `tests.burn.test_std_modules tests.burn.test_doc_blocks`: 6 OK.
- Constant memory: 4 GiB from `/dev/zero` to `/dev/null` through two `File`s, a 1 MiB `read_str` and `write_str` loop: 96 ms best of three, maximum RSS 8.6 MB; 1 MiB the same way: 8.5 MB, 1 GiB 8.5 MB. A 256 MiB random file to a new file: 139 ms best of four, 1.9 GB/s, `cmp` equal; both deleted.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-426]]: wasm32 seek edge cases; `read_bytes`/`write_bytes` are [[MYLA-420]]'s.
