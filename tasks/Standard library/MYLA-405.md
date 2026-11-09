---
id: MYLA-405
title: "CsvError has no message()"
type: improvement
status: backlog
priority: low
labels: [stdlib, csv, errors]
---
Found by the round 3 fixes lane ([[MYLA-332]]). D168 says every module's error type has a `message()` and `Format`; `std.csv`'s `CsvError` has `Format` but no `message()` (`std.xml`'s `XmlError` has both).

- [ ] `CsvError.message()`, its text as `Format` gives it, with a case per kind (`Io` included)
- [ ] [[Language/Standard-library/Csv]]
