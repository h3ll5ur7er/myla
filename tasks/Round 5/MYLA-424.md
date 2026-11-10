---
id: MYLA-424
title: "P10 Structured formats: TOML depth, YAML, JSON ranges"
type: bug
status: todo
priority: medium
labels: [std, toml, yaml, json, round-5]
---
Work package P10 of [[Project/Review-2026-11-09]] (wave A2). Files: `lib/std/toml.my`, `lib/std/yaml.my`, `lib/std/json.my`, `lib/std/xml.my` for its sentence.

- [ ] M20: a nesting limit in std.toml as JSON and YAML have (80 KB of nested inline tables: 28 s and 3 GB; 10^5 `[` overflowed the stack) ([[MYLA-407]])
- [ ] M21: a YAML block scalar whose only line is spaces; raw C0 control characters refused; the writer's YAML 1.1 protection beyond booleans ([[MYLA-349]])
- [ ] `json.to_string` of infinity and NaN doesn't write `Infinity`
- [ ] [[MYLA-385]]'s follow-up: `decode` refuses a `uint64` above 2^63 that would lose its low bits, and -2^63-1 for `int64`
- [ ] The `#derive(Toml)` help text
- [ ] [[MYLA-348]]'s follow-up: the W3C XML suite's place (vendored or fetched as the YAML suite is) and Xml.md's wasm32 sentence
