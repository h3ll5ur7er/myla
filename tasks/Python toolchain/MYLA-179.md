---
id: MYLA-179
title: Map iteration order differs between the interpreter and native code
type: improvement
status: backlog
priority: low
labels: [maps, parity, design]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `for k in m` and `keys(m)` visit keys in insertion order in the Python interpreter (a `dict`) and in hash order natively. [[Language/Collections-and-strings]] says the order is undefined, so it isn't a bug by the page, but it is the one place where "the interpreter is the semantics" is false, and a `#test` can't pin a map's keys. Needs a decision: define insertion order (an order vector in the native map cell, in both backends and the self-hosted interpreter), or sort the keys in `keys` and `for`.

- [ ] A decision on [[Project/Decisions]], then the implementation in all four implementations with a parity program
