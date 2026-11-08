---
id: MYLA-369
title: "A primitive for str ↔ [uint8] in one copy, and StringBuilder capacity"
type: improvement
status: backlog
priority: medium
labels: [stdlib, primitives, performance]
---
Found by three wave 2 lanes. `std.bytes.to_str` ([[MYLA-329]]) appends a byte at a time, `std.io`'s `Read`/`Write` traits ([[MYLA-338]]) gained `read_str`/`write_str` so a descriptor's text isn't converted twice (50 MB of lines took 331 ms with `[uint8]` only, 75 ms with the `str` path), and `std.digest` ([[MYLA-328]]) has its own private `bytes_of`. A library module can't use the raw-memory primitives in the interpreter, and `StringBuilder` can't reserve.

- [ ] A primitive (or builtin methods) converting a `str` to `[uint8]` and back in one allocation and one copy, on every target and in the interpreter
- [ ] `StringBuilder` with a capacity
- [ ] `std.bytes`, `std.io` (perhaps dropping `read_str`/`write_str`) and `std.digest` moved onto them, measured
