---
id: MYLA-332
title: "Small formats: CSV, INI, more JSON"
type: feature
status: backlog
priority: medium
labels: [stdlib, formats, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #52, #53, #54. Text formats in memory. CSV over a stream follows [[MYLA-338]].

- **Owns:** `lib/std/csv.my`, `lib/std/ini.my`, `lib/std/json.my` (additions), `docs/Language/Standard-library/Csv.md`, `docs/Language/Standard-library/Ini.md`, `docs/Language/Standard-library/Json.md`
- **Needs:** [[MYLA-321]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `std.csv`: RFC 4180 read and write (quotes, doubled quotes, CRLF, a header row mapped to names), errors with a line and a column
- [ ] `std.ini`: sections, keys, comments, read and write
- [ ] `std.json`: a pretty printer with an indent, typed getters (`as_int`, `as_str`, `as_list`) and access by a path (`a.b[2]`)
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
