---
id: MYLA-332
title: "Small formats: CSV, INI, more JSON"
type: feature
status: review
priority: medium
labels: [stdlib, formats, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #52, #53, #54. Text formats in memory. CSV over a stream follows [[MYLA-338]].

- **Owns:** `lib/std/csv.my`, `lib/std/ini.my`, `lib/std/json.my` (additions), `docs/Language/Standard-library/Csv.md`, `docs/Language/Standard-library/Ini.md`, `docs/Language/Standard-library/Json.md`
- **Needs:** [[MYLA-321]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `std.csv`: RFC 4180 read and write (quotes, doubled quotes, CRLF, a header row mapped to names), errors with a line and a column
- [ ] `std.csv` over a stream, on `std.io`'s `Read` trait: waits for [[MYLA-338]]
- [x] `std.ini`: sections, keys, comments, read and write
- [x] `std.json`: a pretty printer with an indent, typed getters (`as_int`, `as_str`, `as_list`) and access by a path (`a.b[2]`)
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

Built on b4b85d9 (MYLA-315 and the wave 2 modules merged so far).

- **The modules.** `lib/std/csv.my` (`parse`, `parse_with`, `parse_records`, `parse_records_with`, `write`, `write_with`, `CsvError` with `CsvErrorKind`, a line and a column), `lib/std/ini.my` (`parse`, `new`, `write`, `Ini.get`, `sections`, `keys`, `set`, `IniError` with `IniErrorKind` and a line) and, in `lib/std/json.my`, `pretty`, `at`, `obj`, `arr`, `num`, `text` and the getters `as_int`, `as_float`, `as_str`, `as_bool`, `as_list`, `as_object` on `Json`. Nothing that existed in `std.json` changed. None of the three imports `std.list` or `std.str` (MYLA-360: `std.str`'s cases ran as `std.ini`'s own, so `ini.my` trims with a private helper).
- **Cases.** `build/myla test lib/std/<m>.my --stdlib lib`, interpreted and `--native`: csv 32/32, ini 28/28, json 55/55 (35 new) in both. Mutations (a doubled quote copied without its quote, a lone empty field written unquoted, a closing bracket indented one level too deep) fail 3 csv and 2 json cases.
- **Against Python.** A scratch driver compared `parse` with Python 3.13's `csv.reader(strict=True)` on 23,000 texts (20,000 random from `a b , " "" CR LF CRLF space é`, 3,000 written by Python's `csv.writer`): the same records, or an error from both, for all but the 3,909 texts with a `"` inside an unquoted field, which RFC 4180 and Go refuse and Python keeps. `write` gave Python's `csv.writer` text for 3,000 random row lists. `pretty` gave `json.dumps(v, indent=k, ensure_ascii=False)` for 2,000 random values at indents 0, 1, 2 and 4 (8,000 texts), and `at` agreed with a Python model on 15,774 paths (every path into each value, plus one past each array's end and a missing key per object).
- **Throughput.** Natively, `parse` reads a 50 MB file (673,133 records of nine fields, a fifth quoted, some with doubled quotes or line ends) at 96 MB/s, best of five (0.520 s); Python's `csv.reader` reads it at 42 MB/s.
- **Burn tests.** `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks tests.burn.test_json tests.burn.test_lsp`: OK after a bootstrap, which reached its byte-identical fixed point (11,435,410 bytes) with the new `std.json` embedded.
