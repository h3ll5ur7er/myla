---
id: MYLA-189
title: std.str, std.sort, std.char and format width/precision; the duplicated helpers
type: improvement
status: backlog
priority: medium
labels: [stdlib]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). The standard library has no string functions beyond the builtins (no `split`, `join`, `trim`, `starts_with`, `ends_with`, `index_of`, substring, `<` on strings), no sorting, no `min`/`max`/`abs`, no char classification, and `format` has no width or precision (`1.0/3.0` prints `0.33333333333333331`). The consequence is measurable: `is_digit` is defined twice, `trim`/`trim_end` five times, `starts_with`/`ends_with` four times, a merge sort six times, `slice` four times and `join_*` seven times across `selfhost/`, `tools/` and `std/`.

- [ ] `std.str` (split, join, trim, starts_with, ends_with, index_of, substring, compare), `std.sort` (generic over `Ord`), `std.char` (is_digit, is_alpha, is_space, to_upper, to_lower), `min`/`max`/`abs` in `std.num`
- [ ] Width and precision in `format` and f-strings (a decision: D58 left format specs out)
- [ ] The duplicated helpers in `selfhost/` and `tools/` replaced by the library's

Waits for the decision in [[MYLA-211]] (and [[MYLA-204]]).
