---
id: MYLA-85
title: A builtin that copies a byte range of a string
type: feature
status: done
priority: low
labels: [stdlib, interpreter, selfhost, performance]
---
Myla has no way to take part of a `str` other than copying it byte by byte with `append_byte`. Natively that is fast, but the interpreters run it as interpreted code: `std.io`'s `Reader` ([[MYLA-78]]) copies each line out that way, and reading 1 MB of lines takes about 31 s in the Python interpreter and 10 s in the self-hosted one, against 0.16 s natively (15 MB). JSON parsing ([[MYLA-79]]) and the language server ([[MYLA-80]]) will slice strings constantly.

- [x] Decide the form (a builtin like `slice(s, start, end)`, or `append(sb, s, start, end)`), its bounds behaviour, and record it on [[Project/Decisions]]
- [x] Both checkers, both interpreters, both native backends; parity and bounds tests
- [x] Use it in `std.io` (and the grammar tool's `substr`), and measure the interpreters again

## How

Decision D65 on [[Project/Decisions]]; documented on [[Language/Collections-and-strings]].

- `append(sb, s, start, end)` appends the bytes `s[start..end]`: an overload of the existing builtin, so no new name is reserved (a builtin `slice` would have broken `std.io`'s own `slice` and the grammar tool's `substr`, since user declarations can't reuse builtin names). Bounds must satisfy `0 <= start <= end <= len(s)`; otherwise the interpreters fail with `string range {start}..{end} out of bounds (len {n})` at the call, and native code jumps to the existing `index out of bounds` trap, as string indexing does.
- Python checker and interpreter (`append() takes 2 or 4 argument(s)`, `append start`/`append end` must be `int32`); the Python backend's `__sb_extend` became an entry into a new `__sb_extend_range` that checks the bounds; the self-hosted checker and interpreter (which uses the builtin itself) match the messages; the self-hosted backend checks the bounds inline before its `__sb_append_bytes`.
- `std.io`'s `slice` and the grammar tool's `substr` use it. `read_line` also hoists the buffer and its length out of its scan loop.

## Evidence

- Tests written first and red: 4 unit tests (range, a split "ö" joined again, four out-of-range cases, four type errors), the parity program `string_builder_append_range` (CSV-style field splitting with "λ ö", empty ranges, a copied builder), now also in the self-hosted codegen and interpreter gates, and `examples/errors/runtime_str_range_oob.my`. All four implementations print the same; the self-hosted CLI gives the same runtime error and caret as the Python CLI. The checker gate compares the new messages (4 new snippets).
- Reading lines (the [[MYLA-78]] benchmark): 1 MB in the Python interpreter 31 s → 11.7 s, in the self-hosted interpreter 10 s → 4.8 s; 15 MB natively 0.16 s → 0.086 s (Python backend) and 0.30 s → 0.068 s (self-hosted backend). The rest of the interpreters' time is the interpreted scan for `"\n"`, about 19 evaluated nodes per byte before the hoisting.
- Full run: 487 unit, 4 integration and 410 burn tests pass; the bootstrap reaches its fixed point at 7,611,063 bytes.
