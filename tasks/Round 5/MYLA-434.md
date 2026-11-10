---
id: MYLA-434
title: "Async methods in traits"
type: feature
status: backlog
priority: low
labels: [language, design, concurrency]
---
Found by [[Project/Review-2026-11-10]] (question 3): a trait method can't be async, so there is no async `Read` or `Write`, and every async stream API is written per type (D180).

- [ ] A proposal: what an async trait method means for monomorphisation and for the executor, and what std.io would gain
- [ ] The owner's decision
