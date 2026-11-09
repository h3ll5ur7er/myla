---
id: MYLA-399
title: "Drop Read.read_str and Write.write_str now that str and [uint8] convert in one copy?"
type: improvement
status: backlog
priority: low
labels: [stdlib, io, decision]
---
Found by the platform lane ([[MYLA-369]]). `std.io`'s traits have a method for each kind, `read`/`read_str` and `write`/`write_str` ([[MYLA-338]]), because a `str` became a `[uint8]` only byte by byte: 50 MB of lines took 331 ms through `[uint8]`, 75 ms through `str`. Since [[MYLA-369]] the two convert in one allocation and one copy (`__str_to_bytes`, `__bytes_to_str`), and the measurement turned round: natively, `Buffered` reading through `read` and `bytes.to_str` took 100 to 148 ms (median 106) where `read_str` took 129 to 153 ms (median 132) on the same machine; interpreted, on 2 MB, 6.6 s against 6.1 to 6.5 s ([[Language/Standard-library/Io#speed]]). Why the `[uint8]` path, with two more copies, is faster natively isn't known yet (the cells' size classes, perhaps): worth a look either way.

The owner decides:

- **A. Keep both** (as built): nothing changes for the nine modules with streams (`std.io`, `std.fs`, `std.process`, `std.net`, `std.http`, `std.compress`, `std.archive`, `std.xml`, the tests), and text keeps a method of its own.
- **B. Drop both from the traits** (recommended once the parallel lanes have merged): `Read` is `read` alone, `Write` `write` and `flush`; `Buffered` pulls bytes and keeps its text methods (`read_line`, `read_exact`, `read_to_end`), `BufferedWriter` gains an inherent `write_str`; a stream implements one method less. A `__read` that gives a `[uint8]` would spare the descriptor's conversion.
- **C. Keep `write_str` only**, as a convenience every writer has, and drop `read_str`.

- [ ] The decision, in [[Project/Decisions]]
- [ ] If B or C: the traits, their implementations, the pages and the tests changed, measured again
