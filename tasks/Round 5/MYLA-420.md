---
id: MYLA-420
title: "P6 Text and streams"
type: bug
status: todo
priority: medium
labels: [std, str, io, csv, ini, round-5]
---
Work package P6 of [[Project/Review-2026-11-09]] (wave A2), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `lib/std/str.my`, `lib/std/ini.my`, `lib/std/csv.my`, `lib/std/io.my`. Reopens [[MYLA-321]] and [[MYLA-332]].

- [ ] M16: `trim_end()` of a whitespace-only string ([[MYLA-321]])
- [ ] H9: `ini.parse("[é")` returns an error ([[MYLA-332]]); `IniError` gets `message()` (D168)
- [ ] M17 and S5: `Buffered.read_line` and `read_exact` and `csv.stream_reader` linear in the line's length: a buffer that doesn't copy its tail per read; a shared test stream that gives short reads ([[MYLA-338]])
- [ ] S1: a short `read` gives back a list of its own size, not the cell allocated for the request (wasm32 ran out of memory)
- [ ] D180: `s.bytes()` on `str` in std.str
- [ ] `MemoryStream.seek` overflow; `repeat` reserves its result
- [ ] [[MYLA-339]]'s follow-up: `read_bytes` and `write_bytes` where they are missing
- [ ] M25: two-way string search, so `find` isn't O(n·m) (80 KB haystack, 40 KB needle: 3.2 s)
- [ ] D184 for the modules of this package
