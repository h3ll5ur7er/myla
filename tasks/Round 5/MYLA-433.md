---
id: MYLA-433
title: "Private fields and methods of a pub type"
type: feature
status: backlog
priority: medium
labels: [language, design, visibility]
---
Decision 2 of [[Project/Review-2026-11-09]] §4, for its own design (the owner's choice, 2026-11-10). Today every helper method of a public type is public API and every field writable from outside (`Lru.slot_keys`, `Notifier.id`), so no library type can protect an invariant; D178's `c.len` and `c.len()` may differ from anywhere.

- [ ] A proposal with the alternatives (a `pub` per field and method, Rust's rule; module-private by default; a `priv` marker) and the migration of `lib/std/`
- [ ] The owner's decision, then the build
