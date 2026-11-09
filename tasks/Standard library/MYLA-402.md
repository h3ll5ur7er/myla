---
id: MYLA-402
title: "std.toml writes TOML"
type: feature
status: todo
priority: low
labels: [stdlib, formats, toml]
---
Roadmap row #55 ([[Project/Standard-library-roadmap]]): `std.toml` parses TOML but can't write it. The project tool edits manifests (`myla.toml`) and would use it.

- [ ] A writer for `std.toml`'s document type: tables, arrays of tables, inline tables and arrays, strings (basic, with escapes; multi-line where it reads better), integers, floats (`inf`, `nan`), booleans, dates and times as the parser keeps them
- [ ] Keys quoted only when they must be, dotted keys and table headers in the parser's order, so `parse(to_string(doc)) == doc` round-trips
- [ ] Round-trip cases over the parser's own test documents, and the TOML test suite's valid files where the parser accepts them
- [ ] [[Language/Standard-library/Toml]] and the roadmap row
