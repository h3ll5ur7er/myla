---
id: MYLA-362
title: "wasm32: list_dir returned short lists after 64 directory opens"
type: bug
status: review
priority: medium
labels: [wasm, fs]
---
Found by the `std.glob` lane ([[MYLA-326]]). `platform_wasm.dir_read` keeps each descriptor's readdir cookie in slot `fd & 63` of `__wasi_cookies`, and `open_dir` never reset it. Node's shim doesn't reuse descriptor numbers, so after 64 opens a new descriptor found an old cookie, and `fs.list_dir` gave a short or empty list. Under Node, listing two directories 40 times each gave `6 3` for 32 rounds, then `0 0`. A runtime that reuses numbers could hit it from the second listing on.

- [x] `open_dir` zeroes its descriptor's slot ([[lib/std/platform_wasm.my]], commit `da0278a`)
- [x] A burn test in the wasm32 target suite: 100 listings of the same directories, each count unchanged

## Evidence

- `tests/burn/test_fs.py`'s `DirectoryParity.test_the_same_directories_listed_again` (program `RELIST`): in a fresh working directory with `a` (6 files) and `b` (3 files), it lists both 100 times each and prints a round whose counts differ from the first; it expects `6 3` and `done` alone, from the self-hosted interpreter and natively. `test_fs` is in `tests/burn/_targets.py`'s `SUITES`, so `scripts/test-target.py wasm32-wasi` runs it under Node.
- Before: with `open_dir`'s reset of the cookie taken out of `lib/std/platform_wasm.my` (scratch, not committed), `python3 scripts/test-target.py wasm32-wasi tests.burn.test_fs.DirectoryParity.test_the_same_directories_listed_again` fails natively with `6 3\nround 33: 0 0\nround 34: 0 0\n…`.
- After (the code as it is): that test passes on wasm32; the whole `test_fs` passes on x86-64 (19 tests), on wasm32 (`scripts/test-target.py wasm32-wasi tests.burn.test_fs`, 20 s) and on aarch64 (`scripts/test-target.py aarch64-linux tests.burn.test_fs`, 8 s).
