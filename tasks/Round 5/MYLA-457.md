---
id: MYLA-457
title: "A write to a full non-blocking descriptor spins"
type: bug
status: done
priority: low
labels: [runtime, platform, io, round-5]
---
Found by [[MYLA-419]]. `std.platform`'s `write_all`, under `__write` and `__write_bytes` (`print`, `println`, `FdStream`, `File`, a child's input), retries a write that gave EAGAIN at once, so a program whose standard output is a non-blocking pipe (as a parent like Node or an event loop may hand it) spins on the CPU for as long as the reader is slow, where a blocking write would sleep. Measured: 2 MiB printed to a non-blocking pipe read 64 KiB every 10 ms took 0.34 s, and the writer used 0.29 s of CPU (with a blocking pipe, about 0.01 s).

```myla
from std.io import println

fun main() {
    let line = "x".repeat(1023)
    for i in 0..2048 {
        println(line)
    }
}
```

Run with its stdout the write end of a pipe set `O_NONBLOCK` (Python: `os.set_blocking(w, False)`), the reader sleeping between reads.

- [x] On EAGAIN, wait for room (`os.poll_write(fd, -1)`, which [[MYLA-419]] added) before writing again, on x86-64 and aarch64; WASI's `fd_write` is blocking already
- [x] A burn test with a non-blocking standard output, which measures the writer's CPU time

## What changed

- `std.platform`'s `write_all` and `write_line` on x86-64 and aarch64 wait in `poll_write(fd, -1)` on EAGAIN, then write again: the thread sleeps as a blocking write's would. `print`, `println`, `__write`, `__write_bytes` (an `FdStream`, a `File`, a child's input) and the interpreter's own writes (it is a native program on the same runtime) all go through them.
- In a task, `FdStream.write_async(b)` (new) waits with the task suspended (`await __wait_writable`), a PIPE_BUF piece at a time, as `ChildStdin.write_async` does; a synchronous write in a task blocks its worker in the poll, as a blocking descriptor's write does (it can't suspend: `print` is no async function).
- wasm32: the program never saw EAGAIN, as the task says, but Node's shim (`tools/wasm/node_fs.mjs`'s `writeAll`) tried again at once and spun the same way (0.69 s of CPU over 0.71 s); it now sleeps a millisecond on EAGAIN (Node has no synchronous poll).

## Evidence

`NonBlockingOutput` in `tests/burn/test_stdio.py`: 2 MiB through `print`, `println` and an `FdStream`, and through `write_async` in a task beside a sleeping one, into a non-blocking pipe read 64 KiB every 20 ms, interpreted and built; it measures the writer's CPU time (`wait4`) against the wall time.

- Before: `0.63 s of CPU in 0.69 s` interpreted, `0.60 s of CPU in 0.65 s` built, and `FdStream` had no `write_async`.
- After (CPU in wall): sync interpreted 0.034 s in 0.69 s, built 0.002 s in 0.67 s; async interpreted 0.083 s in 0.73 s, built 0.015 s in 0.69 s. On aarch64 (qemu) 0.012 and 0.20 s built; on wasm32 (Node) 0.69 s before the shim's change, 0.09 and 0.13 s after (mostly Node's start).
- `tests.burn.test_stdio`: 16 OK natively and with `MYLA_TEST_TARGET=aarch64-linux`; on wasm32 the one failure is `test_a_write_to_another_descriptor_reports_it`, which `_targets` excuses there.

## Review 2026-11-12

Built and merged (`b415e497`) while still `backlog`. Measured in [[Project/Review-2026-11-12]]: 2 MiB to a non-blocking standard output cost 0.001 s of CPU (0.306 s before). Signed off.
