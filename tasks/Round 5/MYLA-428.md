---
id: MYLA-428
title: "P14 Standard library helpers, round two"
type: improvement
status: todo
priority: low
labels: [std, cleanup, round-5]
---
Work package P14 of [[Project/Review-2026-11-09]] (wave B, after wave A: it touches twenty modules wave A edits). Follow-up of [[MYLA-376]].

- [ ] `holds` ×5 (a workaround for a bug [[MYLA-355]] fixed)
- [ ] `is_some_of`, `is_none` and `same` in deque, heap, random and set
- [ ] `hex_digit` ×6, `unhex` ×3, `hex_of` ×3; `is_digit`, `digit_value`, `utf8_len`, `find_byte`
- [ ] std.toml's private `utf8_error`; std.compress's own CRC-32 and Adler-32
