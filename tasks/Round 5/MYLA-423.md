---
id: MYLA-423
title: "P9 Archives and compression: pax numbers, ids, output limits"
type: bug
status: todo
priority: medium
labels: [std, archive, compress, round-5]
---
Work package P9 of [[Project/Review-2026-11-09]] (wave A2). Files: `lib/std/archive.my`, `lib/std/compress.my`, `tests/burn/test_archive.py`. Reopens [[MYLA-352]].

- [ ] `pax_int` bounded (a 20-digit pax number overflowed), D184
- [ ] M19: uid and gid of 2^31 or more as `int64`, or refused
- [ ] A `max_output` form of `inflate`, `gunzip` and `zip_data`
- [ ] Tar headers and pax records in the fuzz test, run under `--checked`
