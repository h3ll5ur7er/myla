---
id: MYLA-572
title: "A read of n bytes from a descriptor allocates n bytes before it reads"
type: bug
status: review
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

- [x] A read's room capped, so `read(2000000000)` of a short input takes little memory, natively on every target and interpreted
- [x] A case that reads with a huge count under a memory limit (or counts the room asked for)

## What changed

`std.rt`'s `read`, `read_bytes` and `sock_recv` (the `__read`, `__read_bytes` and `__sock_recv` of every stream: `FdStream`, `File`, a child's pipes, `TcpStream`, the terminal) take room for at most `READ_ROOM`, 4 MiB, whatever count they are given (`read_room`, [[lib/std/rt.my]]). A read may give fewer bytes than asked (D177), so callers see the same bytes, in more reads only when one read could have given more than 4 MiB (a regular file, a pipe never gives more than its buffer). The interpreter's `__read` and `__read_bytes` are the toolchain's own `std.rt` calls, so interpreted runs are capped too after the bootstrap. A datagram's `__sock_recv_from` keeps its count: a datagram is cut to the room. `fitted` (MYLA-420) still gives a short read's cell back. Documented on [[Language/Standard-library/Io]] beside MYLA-420's paragraph.

## Evidence

- The task's program (with `VmPeak` printed before and after): natively before, `16652 kB`, `4 bytes`, `1969804 kB`, and under `ulimit -v 400000` `runtime error: out of memory`; after, `16656 kB`, `4 bytes`, `16656 kB`, and the same under the limit. aarch64 (qemu): 240,408 → 2,193,688 kB before, 240,408 → 240,540 kB after. wasm32 (Node): the linear memory 2,025,390,080 bytes before, 25,362,432 after. Interpreted (`myla run`): 96,448 → 2,049,760 kB before, and `out of memory` under the limit.
- The burn test `test_stdio.HugeReads.test_a_huge_count_costs_the_room_of_a_few_mib` (interpreted and native: the program's own `VmPeak` growth under 64 MiB; on wasm32 the linear memory's peak): before the fix `1953424 not less than 65536` interpreted, `1953152` natively, and on wasm32 `2025390080 not less than 67108864`; after, OK natively, on aarch64 and on wasm32.
- Suites at the end: `scripts/test.sh fast` (886 tests) and `scripts/test.sh` (1,626 tests, 342 skipped): the one failure `test_embedded_std`, as expected until the integrator's seed; `scripts/test-target.py aarch64-linux` and `wasm32-wasi` for `test_stdio`, `test_net` and `test_term`; the platform modules' own cases on their targets (23, 23, 19), which first found `__on_raw_signal` named wrongly when std.platform is the entry (fixed, `platform_fn`).
