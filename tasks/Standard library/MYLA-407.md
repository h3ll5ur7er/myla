---
id: MYLA-407
title: "std.toml reads and writes TOML 1.0; #derive(Toml)"
type: feature
status: todo
priority: medium
labels: [stdlib, formats, toml, derive]
---
The owner's decision on [[MYLA-402]]'s scope (2026-11-09): extend std.toml so that what the writer writes, the parser reads back, and add a derive for TOML as [[MYLA-385]] did for JSON.

- [ ] The parser reads TOML 1.0: floats (`inf`, `nan`, exponents, underscores), integers in hex, octal and binary, offset and local date-times, dates and times, multi-line and literal strings, dotted keys, inline tables, arrays of any values, arrays of tables (`[[x]]`); the errors keep their line and column
- [ ] `Toml` gains the variants it needs (`Float`, the date and time kinds); `selfhost/project.my` and `tools/lsp/projects.my`, which match on it, updated
- [ ] The writer writes every variant, so `parse(to_string(doc)) == doc` for every document `parse` gives; the toml-test suite's valid TOML 1.0 files read and written back (none refused), its invalid ones refused
- [ ] `#derive(Toml)`: `ToToml` and `FromToml` traits in std.toml, `encode` and `decode<T>`, generated as source as `#derive(Json)` is (D172), on structs and enums, generic types included (bounded per parameter, as [[MYLA-379]] does); the error corpus and parity programs
- [ ] [[Language/Standard-library/Toml]], [[Language/Methods-and-traits]] (the derive), the myla skill
