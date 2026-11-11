---
id: MYLA-457
title: "A write to a full non-blocking descriptor spins"
type: bug
status: backlog
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

- [ ] On EAGAIN, wait for room (`os.poll_write(fd, -1)`, which [[MYLA-419]] added) before writing again, on x86-64 and aarch64; WASI's `fd_write` is blocking already
- [ ] A burn test with a non-blocking standard output, which measures the writer's CPU time
