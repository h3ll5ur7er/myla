---
id: MYLA-353
title: "Decision: iterators and for over a trait"
type: chore
status: backlog
priority: low
labels: [decision, language, stdlib, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #21. Whether Myla gets an `Iterator` trait, and with it `for x in it` over any type implementing it and lazy adapters (`map`, `filter`, `take`), so a pipeline doesn't build a list at each step. A language decision first: what `for` desugars to, how an adapter holds the closure and the iterator it wraps by value, and what that costs natively.

- **Needs:** nothing; it can start as soon as its wave does

- [ ] Options and a recommendation written here for the owner
- [ ] The decision recorded
