---
id: MYLA-354
title: "Decision: serialisation by derive"
type: chore
status: backlog
priority: low
labels: [decision, language, stdlib, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #58. Whether `#derive(Json)` (or a serialisation trait with a derive, as `Eq` and `Hash` have) converts structs and enums to and from `std.json`'s values, and later TOML and YAML. A language decision first: what the derive generates, field names and renames, `Option` fields, enums.

- **Needs:** [[MYLA-332]]

- [ ] Options and a recommendation written here for the owner
- [ ] The decision recorded
