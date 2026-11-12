---
id: MYLA-546
title: "R4 The interpreter: small differences from native code, and the cost that crept in"
type: bug
status: todo
priority: low
labels: [interpreter, round-6]
---
Work package R4 of [[Project/Review-2026-11-12]]. Files: `selfhost/interp.my`. Same lane as [[MYLA-414]] (reopened).

- [ ] The REPL echoes a `uint64` of 2^63 or more signed
- [ ] A `uint64` index of 2^64-1 is reported as -1 in `list index … out of bounds` (both runners; [[MYLA-440]])
- [ ] A map's order differs from native code's when written hashes collide (the number of `eq` calls differs too) and in a nested map literal ([[MYLA-506]])
- [ ] The plain loop got 8.6 percent slower over round 5, each task having measured against its own base. Add a row without a map to the benchmark table and find the step
- [ ] Packed bytes through `extend` and `read_line` are still slow interpreted (3 MB in 60,000 lines: 9.1 s)
- [ ] Large legitimate arguments: `math.ldexp(x, ±2^30)` takes over 5 s, `fmt.fmt_text("xy", ">1000000")` 6.4 s against 13 ms natively, `to_hex(n, 2^30)` pads one character at a time
- [ ] An idle interpreted HTTP server uses 23 percent of a CPU with 1,000 parked connections (`repro-r5/http/t_idlecpu.py`); natively none
- [ ] `docs/Language/Generics.md`, first line: generic code is no longer "run by erasure" in the interpreter since [[MYLA-414]] binds the type parameters
