---
id: MYLA-332
title: "Small formats: CSV, INI, more JSON"
type: feature
status: todo
priority: medium
labels: [stdlib, formats, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #52, #53, #54. Text formats in memory. CSV over a stream follows [[MYLA-338]].

- **Owns:** `lib/std/csv.my`, `lib/std/ini.my`, `lib/std/json.my` (additions), `docs/Language/Standard-library/Csv.md`, `docs/Language/Standard-library/Ini.md`, `docs/Language/Standard-library/Json.md`
- **Needs:** [[MYLA-321]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `std.csv`: RFC 4180 read and write (quotes, doubled quotes, CRLF, a header row mapped to names), errors with a line and a column
- [x] `std.csv` over a stream, on `std.io`'s `Read` trait (after [[MYLA-338]])
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

### The stream reader (round 3, 2026-11-09)

Built on 7b328dd.

- **The module.** `lib/std/csv.my` has `stream_reader(r)` and `stream_reader_with(r, delim)` for any `R: Read`, giving a `CsvStreamReader<R>` with `read_record()` (`Result<Option<[str]>, CsvError>`), `io_error()` and an `impl Iterator<Result<[str], CsvError>>`. It keeps the stream as `std.io`'s `Buffered` does (`src: [R]`) and the bytes read but not used in the in-memory `Reader`, which now knows the line, column and CR state of its first byte (`line0`, `col0`, `cr0`): a read drops what was used. A record is taken once its line end or the end of the stream is in; one that reaches the end of the bytes read so far is read again after the next read, which doubles while one record needs more (64 KiB at first), so a long record costs linear time. Only `UnclosedQuote` can change with more bytes; the other errors are given at once. A new `CsvErrorKind.Io` (no payload, so `CsvError` stays `Eq`) is a failed read, at the end of what was read, with the cause in `io_error()`, as `std.xml`'s stream reader has it. `std.csv` now imports `std.io`'s `Read` and `from_str` and `std.fs`'s `IoError`.
- **Cases.** Three test functions and three cases: `stream_as_parse` reads 21 texts (doubled quotes, CRLF, lone CR, blank lines, a CR at the end, every error with its position, multi-byte characters) with reads of every size from 1 byte to the whole text and compares with `parse`, plus a tab-delimited text and `write`'s output; `stream_holds_a_chunk` reads 5,000 records (97,780 bytes) with 256-byte reads and checks that the buffer never held 1 KB, then a quoted record of 250,000 bytes with reads from 1 byte (and that the read size is back to its first after it); `stream_failure` a stream that fails after its first read. `build/myla test lib/std/csv.my --stdlib lib`: 38/38 interpreted, `--native`, `--target wasm32-wasi` (Node) and `--target aarch64-linux` (qemu). Mutations: accepting a record that reaches the end of the bytes read fails all three test functions; not carrying the CR state across a read fails `stream_as_parse`; reads that don't double make the 250,000-byte record quadratic (the interpreted run didn't end in 10 minutes).
- **Measured** natively on a 50 MB file (359,208 records of nine fields, written by Python's `csv.writer` from random rows, about a quarter of the fields quoted), best of five: `csv.stream_reader(fs.open(path))` 0.536 s (93 MB/s), peak RSS 8.6 MB; `fs.read_to_string` and `csv.parse` 0.513 s (97 MB/s), 240 MB. The same 359,208 records and 3,232,872 fields from both; Python 3's `csv.reader` reads the file in 0.684 s.
- **The page.** [[Language/Standard-library/Csv]] has a section "Reading a stream" with a doc block that runs, the functions and methods, the `Io` error kind and the measurement; the index row on [[Language/Standard-library]] names the stream reader.
- **Not done, on purpose:** no stream form of `parse_records` (records mapped by the header): the header is the first record, and the page says so. It can follow if someone asks.

## Comments

- 2026-11-09: the owner confirmed a failed read as `CsvErrorKind.Io` with the cause in `io_error()`, over an error that wraps an `IoError`.

## Review 2026-11-09

Not ready ([[Project/Review-2026-11-09]]): `ini.parse("[é")` ends the program (H9); the CSV stream reader is quadratic on short reads (M17). The fix is in [[MYLA-420]].

- [ ] The review's blocker, fixed with [[MYLA-420]]
