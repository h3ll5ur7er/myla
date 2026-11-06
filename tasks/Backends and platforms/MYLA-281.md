---
id: MYLA-281
title: "wasm32: the file system as the other targets show it"
type: bug
status: backlog
priority: low
labels: [platforms, wasm, io]
---
Found by the per-target suites ([[MYLA-268]], `scripts/test-target.py wasm32-wasi`). Under WASI (Node's shim, `tools/wasm/run.mjs`) three things differ from x86-64, aarch64 and the interpreter; `tests/burn/_targets.py` excuses the tests until they agree:

- Reading a directory gives `IoError.Other` ("I/O error"), not `IsADirectory` ("a directory, not a file"): `test_fs.TestReadFileExample.test_a_directory`, `test_fs.TestWriteToFileParity.test_directory_read_is_a_directory`. WASI's `path_open` on a directory succeeds and `fd_read` then fails with `EISDIR` or `EBADF`; `std.platform` (`lib/std/platform_wasm.my`) should map that read error to `IsADirectory`.
- `test_fs.DirectoryParity.test_tour`: one of the tour's paths reads as `exists false dir false` (the others agree). Find which (the tour's output, line by line) and why.
- `test_fs.DirectoryParity.test_current_dir_removed`: with the working directory removed, Node itself fails at start-up (`process.cwd()` in its bootstrap) before the program runs. `run.mjs` should start in a directory that exists and preopen the program's directory as it was, or report the error as the other targets do (`not found`).

- [ ] `IsADirectory` for a directory read
- [ ] The tour's path
- [ ] A removed working directory
- [ ] The tests out of `_targets.py`'s wasm32 list
