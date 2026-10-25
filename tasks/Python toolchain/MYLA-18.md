---
id: MYLA-18
title: "Strings from +, format and builders are never freed"
type: improvement
status: backlog
priority: low
labels: [native-backend, memory]
---
`str` values are not reference-counted: results of `+`, `format`, `build`, `chars` input and `std` I/O live in the arena until the process exits ("arena-resident, by design", D41 note in [[Project/Decisions]]). The arena is 1 GiB, and running out traps silently.

Fine for the compiler; a long-running program that builds strings in a loop eventually dies.

## Done when

- [ ] Decide whether `str` joins reference counting (heap strings get a header; literals stay static with a sentinel refcount)
- [ ] If yes: retain/drop strings like lists, in both native backends
