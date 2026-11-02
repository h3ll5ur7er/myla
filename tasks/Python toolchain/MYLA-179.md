---
id: MYLA-179
title: Map iteration order differs between the interpreter and native code
type: improvement
status: todo
priority: low
labels: [maps, parity, design]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `for k in m` and `keys(m)` visit keys in insertion order in the Python interpreter (a `dict`) and in hash order natively. [[Language/Collections-and-strings]] says the order is undefined, so it isn't a bug by the page, but it is the one place where "the interpreter is the semantics" is false, and a `#test` can't pin a map's keys. Needs a decision: define insertion order (an order vector in the native map cell, in both backends and the self-hosted interpreter), or sort the keys in `keys` and `for`.


Part of the language ergonomics round ([[MYLA-215]]).

## Options

- **A. Undefined, as documented.** Nothing changes; `#test` cases can't show a map's keys and the interpreters and native code keep disagreeing.
- **B. Insertion order** in all four implementations: an order vector in the native map cell (removal leaves a tombstone or compacts). Matches Python's `dict`, so the oracle needs no change; deterministic output.
- **C. Sorted order** for `keys` and `for`: needs an ordering on every key type, and costs a sort per iteration.

## Recommendation

**B.** Deterministic and testable, the cheapest for the oracle, and what users of Python and Swift's ordered collections expect.

## Decision

**D105 (2026-11-01): insertion order** (option B), in every implementation (after [[MYLA-219]], the self-hosted interpreter and the native map).

- [x] A decision on [[Project/Decisions]] (D105)
- [ ] Then the implementation in all four implementations with a parity program
