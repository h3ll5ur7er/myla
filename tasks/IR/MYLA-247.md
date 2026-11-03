---
id: MYLA-247
title: Packed list elements
type: improvement
status: backlog
priority: medium
labels: [backend, runtime, performance, memory]
---
Found by the first benchmark round ([[MYLA-242]]). A list element takes 8 bytes whatever its type: `stored_size` of a scalar is its 8-byte slot (the IR is "close to the machine", scalars are 8-byte values). So a `[bool]` or `[uint8]` takes eight times the memory C uses.

The sieve over 40 million flags peaked at 817 MB, against C's 40 MB:
- the capacity rounds up to 2²⁶ slots × 8 bytes = 537 MB;
- the previous buffer, 268 MB, is still held during the last copy.

The 209,000 page faults cost about as much system time as the whole C program runs. Strings are bytes already.

- [ ] Elements stored at their natural size in lists (`bool`, `uint8`/`int8` 1 byte, 16-bit 2, 32-bit and `float32` 4, `char` 4), loaded and stored with the matching width and extended into the 8-byte slot on load
- [ ] Everything that walks a list's elements: the IR's element instructions ([[Architecture/IR]]), the runtime's list routines, copy-on-write copies, `==` where it applies, the gdb printers and DWARF descriptions ([[MYLA-66]])
- [ ] Measured: the sieve's memory and time ([[MYLA-242]]), and the self-compile
