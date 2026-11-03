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

## Plan (2026-11-03, from the optimisation pass of [[MYLA-242]])

Left for its own round: element addresses flow into the lowering's general handling of places, so a packed list read with an 8-byte load anywhere would silently combine neighbouring elements. A hurried change risks wrong results rather than a failing build.

- **Where element addresses come from:** `elem_read` and the index-assignment place ([[selfhost/lower.my]]), `push_elem` (`Append`), `pop_elem` (`Pop`), list literals (`store_member` at `16 + i * stride`). All take the stride from `stored_size`.
- **Where they go:** the reads and stores of places (`LoadAt`/`StoreAt`, always 8 bytes), compound assignment on an element, `for` over a list, `match` on an element, `store_staged`. Strings already have the one narrow path (`Load8` for a byte).
- **The change:** a width on `LoadAt`/`StoreAt`, or a narrow load and store of their own beside `Load8`, chosen from the element type wherever a list element is read or written. The IR verifier and the text form show it; `ir_x86` emits `movzbl`/`movsbq`/`movb`, the 16- and 32-bit forms and `movss` for `float32`.
- **In two steps:**
  1. `[bool]` first: no runtime routine builds one, so the hand-written assembly stays as it is; it covers the sieve (817 MB) and Game of Life's rows.
  2. Then the types the runtime builds lists of: `keys()` of a map (its key type), `chars()` (`[char]`, 4 bytes), a process's output (`[uint8]`), and `[int32]` for quicksort and closures.
- **Also:** the DWARF description of a list's elements and the gdb printer ([[MYLA-66]], `lib/debug/myla_gdb.py`), which read 8-byte elements.
- **The test first:** every element path (read, write, compound assignment, `for`, `match`, push, pop, literal, copy-on-write clone) on packed lists, against the interpreter.
