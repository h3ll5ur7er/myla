---
id: MYLA-321
title: "std.str: search, split, join, trim, case, replace"
type: feature
status: todo
priority: high
labels: [stdlib, strings, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]], roadmap #1, #2, #3, #4. Methods on `str` (`impl str`), byte-wise, ASCII for case. AoC's `text.my` is the reference for what is used most ([[Project/AoC-2015-2021]]). `join` is a method of `[str]` and so lives with [[MYLA-323]]'s lists in `std.list`.

- **Owns:** `lib/std/str.my`, `docs/Language/Standard-library/Str.md`
- **Needs:** [[MYLA-319]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] Search: `find`, `rfind`, `find_from`, `contains`, `starts_with`, `ends_with`, `count`
- [ ] Split: `split(sep)`, `splitn`, `words`, `lines` (a final `\n` gives no empty last line; `\r\n` handled)
- [ ] Trim and case: `trim`, `trim_start`, `trim_end`, `strip_prefix`, `strip_suffix` (an `Option`), ASCII `to_upper`, `to_lower`, `repeat(n)`, `pad_start`, `pad_end`
- [ ] Replace: `replace(from, to)`, `replacen`
- [ ] Measured against a hand-written loop on a 10 MB string: within 1.5 times of it, natively
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
