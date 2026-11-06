---
id: MYLA-281
title: "wasm32: the file system as the other targets show it"
type: bug
status: done
priority: low
labels: [platforms, wasm, io]
---
Found by the per-target suites ([[MYLA-268]], `scripts/test-target.py wasm32-wasi`). Under WASI (Node's shim, `tools/wasm/run.mjs`) three things differ from x86-64, aarch64 and the interpreter; `tests/burn/_targets.py` excuses the tests until they agree:

- Reading a directory gives `IoError.Other` ("I/O error"), not `IsADirectory` ("a directory, not a file"): `test_fs.TestReadFileExample.test_a_directory`, `test_fs.TestWriteToFileParity.test_directory_read_is_a_directory`. WASI's `path_open` on a directory succeeds and `fd_read` then fails with `EISDIR` or `EBADF`; `std.platform` (`lib/std/platform_wasm.my`) should map that read error to `IsADirectory`.
- `test_fs.DirectoryParity.test_tour`: one of the tour's paths reads as `exists false dir false` (the others agree). Find which (the tour's output, line by line) and why.
- `test_fs.DirectoryParity.test_current_dir_removed`: with the working directory removed, Node itself fails at start-up (`process.cwd()` in its bootstrap) before the program runs. `run.mjs` should start in a directory that exists and preopen the program's directory as it was, or report the error as the other targets do (`not found`).

- [x] `IsADirectory` for a directory read
- [x] The tour's path
- [x] A removed working directory
- [x] The tests out of `_targets.py`'s wasm32 list

## Evidence (2026-11-06)

All three in `lib/std/platform_wasm.my`, so on any WASI host, not only Node's shim:
- **A directory read.** WASI refuses it with EBADF (a directory's descriptor has no read right); `read` turns a refused read of a descriptor whose filestat says directory into Linux's EISDIR, which `std.io` reports as `IsADirectory`.
- **The tour's path** was `''`: Linux's `stat("")` is ENOENT, WASI took the empty path for the preopened directory itself. Every path operation (`on_path`) now refuses an empty path with ENOENT.
- **A removed working directory.** `run.mjs` read `process.cwd()` for `PWD`, which throws there: it now keeps the `PWD` the shell left. And `cwd()`, as Linux's `getcwd`, is ENOENT when `PWD` names nothing any more (the preopen is `/`, so the path itself is checked).
- `scripts/test-target.py wasm32-wasi test_fs` passes with none of the four exceptions; `test_wasm` passes.
