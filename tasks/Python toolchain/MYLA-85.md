---
id: MYLA-85
title: A builtin that copies a byte range of a string
type: feature
status: backlog
priority: low
labels: [stdlib, interpreter, selfhost, performance]
---
Myla has no way to take part of a `str` other than copying it byte by byte with `append_byte`. Natively that is fast, but the interpreters run it as interpreted code: `std.io`'s `Reader` ([[MYLA-78]]) copies each line out that way, and reading 1 MB of lines takes about 31 s in the Python interpreter and 10 s in the self-hosted one, against 0.16 s natively (15 MB). JSON parsing ([[MYLA-79]]) and the language server ([[MYLA-80]]) will slice strings constantly.

- [ ] Decide the form (a builtin like `slice(s, start, end)`, or `append(sb, s, start, end)`), its bounds behaviour, and record it on [[Project/Decisions]]
- [ ] Both checkers, both interpreters, both native backends; parity and bounds tests
- [ ] Use it in `std.io` (and the grammar tool's `substr`), and measure the interpreters again
