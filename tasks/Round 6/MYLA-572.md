---
id: MYLA-572
title: "A read of n bytes from a descriptor allocates n bytes before it reads"
type: bug
status: todo
priority: low
labels: [std, runtime, io, round-6]
---
Found by [[MYLA-550]] (the library A lane of round 6), beside its `read_exact` item. `std.rt`'s `read_bytes` (`__read_bytes`, [[lib/std/rt.my]]), which `FdStream.read(n)`, `fs.File.read(n)` and a child's pipes use, allocates room for `n` bytes and then reads, so a large count costs its size in memory whatever the stream holds. `read(n)` may give fewer bytes than asked (D177), so the room could be capped (a few MiB a read, or what `fstat` says is left of a regular file) without changing what a caller sees but the number of reads.

```myla
import std.io as io
from std.io import Read

fun main() {
    var r = io.fd_stream(0)
    match r.read(2000000000) {
        Ok(b) => print(f"{b.len()} bytes")
        Err(e) => print(f"error {e}")
    }
}
```

Natively, x86-64: `echo abc | ./bigread` prints `4 bytes`; under `ulimit -v 400000` it is `runtime error: out of memory`. `Buffered.read_exact` no longer asks for such counts ([[MYLA-550]]), but `Buffered.read(n)` with `n` of 4 KiB or more passes `n` on to the stream, and so does any program's own `read`.

- [ ] A read's room capped, so `read(2000000000)` of a short input takes little memory, natively on every target and interpreted
- [ ] A case that reads with a huge count under a memory limit (or counts the room asked for)
