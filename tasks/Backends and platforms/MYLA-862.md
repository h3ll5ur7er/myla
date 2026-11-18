---
id: MYLA-862
title: "Linux's run_with takes a failed read of a child's pipe for its end"
type: bug
status: review
priority: low
labels: [platforms, stdlib]
---
Found by [[MYLA-798]], which made a read of a child's pipe that fails `Other` of its cause in std.process's `collect_async` ([[lib/std/process.my]]) and in Windows' `run_with` ([[lib/std/platform_windows.my]]). Linux's `run_with` ([[lib/std/platform.my]], and its aarch64 copy) still reads the two pipes with `read_some`, which gives -1 "at the end of the file or on an error": a pipe that fails to read ends that stream, and `run` and `output` give `Ok` with the output cut short and nothing said. On Linux a read of a pipe hardly fails (EIO, ENOMEM), which is why it is low.

- [x] `read_some` tells the end from an error, and `run_with` records the first error's cause as the run's (`__set_run_status(code, sig, cause)`), as Windows' does
- [x] the same in `platform_aarch64.my`; a `#test` or a burn test where one can be made to fail (a descriptor closed under it)

## What changed

- **`run_with`** ([[lib/std/platform.my]], and `platform_aarch64.my` until [[MYLA-758]] made them one): `read_some` is gone; each pipe's read is `sys(SYS_READ, …)` itself, which tells the end (0) from a failure (minus its cause) and EINTR (read again). The first failed read's cause, and a failed `poll`'s, is kept in `failed`; the stream still ends there and the other is read on, and once the child is reaped `__set_run_status(code, sig, failed)` records it with its exit status, as Windows' `run_with` does ([[MYLA-798]]). std.process's `collect` then gives `Err(SpawnError.Other(5))` for an EIO (its comment says so). Windows' `run_with` and `collect_async` needed nothing: [[MYLA-798]] did them.
- **The test** is a burn test, `tests/burn/test_process.py`'s `FailedPipeRead`: no `#test` can make a read fail, since the interpreter runs no system calls. strace's fault injection (`-e inject=read:error=EIO:when=3`) makes the parent's third read fail: `run`'s first child's, after the exec report's. The second child's reads go through. It runs natively on x86-64 where strace is installed, and is skipped elsewhere: under qemu it would trace qemu's own reads.
- **Docs**: [[Language/Standard-library/Process]]'s `run` row.

## Evidence

- **Before** (BASE `3add216`): `FailedPipeRead` failed. The program printed `ok 4 0` (`Ok`, with the 4 bytes of stderr lost and nothing said) where `other 5` is expected. With every pipe read failing (`when=2+`) it printed `ok 0 0` twice.
- **After**: it prints `other 5` and then `ok 4 0`, and `tests.burn.test_process` passes, 14 tests (3 skipped). `scripts/test-target.py aarch64-linux tests.burn.test_process` passes (4 skipped, the new test among them). The module cases pass: `build/myla test lib/std/platform.my` 54/54 (interpreted and `--native`), `platform_aarch64.my` 54/54 (interpreted and `--target aarch64-linux`), and `process.my` 53/53 (interpreted and `--native`).
