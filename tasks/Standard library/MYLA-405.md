---
id: MYLA-405
title: "CsvError has no message()"
type: improvement
status: review
priority: low
labels: [stdlib, csv, errors]
---
Found by the round 3 fixes lane ([[MYLA-332]]). D168 says every module's error type has a `message()` and `Format`; `std.csv`'s `CsvError` has `Format` but no `message()` (`std.xml`'s `XmlError` has both).

- [x] `CsvError.message()`, its text as `Format` gives it, with a case per kind (`Io` included)
- [x] [[Language/Standard-library/Csv]]

## Evidence

Built on `9681bb3` (after [[MYLA-399]] in the streams lane).

- **Before:** `e.message()` of a `csv.parse` error: `type error: type 'csv.CsvError' has no method 'message'`. After: `'"' in an unquoted field`, and `f"{e}"` `1:2: '"' in an unquoted field`.
- [[lib/std/csv.my]]: `impl CsvError { fun message(self) -> str }` with a case per kind (`BareQuote`, `UnclosedQuote`, `AfterQuote`, `FieldCount`, `DuplicateName`, `Io`); `Format` writes `line:col: ` and `message()`, as std.xml's does, its three cases unchanged. `build/myla test lib/std/csv.my --stdlib lib`: 44/44 (38 before) interpreted and `--native`.
- [[Language/Standard-library/Csv]]: the errors' table has each kind's message; the page names `message()`.
