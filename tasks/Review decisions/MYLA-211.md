---
id: MYLA-211
title: "Decision: the standard-library round, its scope, API shape and order"
type: chore
status: review
priority: medium
labels: [decision, stdlib]
---
From the October 2026 review ([[Project/Review-2026-10]], §13.4). Missing: `std.str`, `std.sort`, `std.char`, format width and precision, `min`/`max`/`abs`, a clock, environment access, file handles (`open` → a reader, streaming writes), `std.process` with PATH, cwd, env and stdin. About 25 helpers are duplicated across the repository for want of them. Implementation tasks: [[MYLA-189]], [[MYLA-190]].

## Question

Which modules come first, and what shape do their APIs take?

## Sub-questions and options

- **Call style**: methods (`s.split(",")`) or functions (`str.split(s, ",")`): follows [[MYLA-204]], which should be decided first.
- **Sorting**: an `Ord` trait (today `cannot derive 'Ord'`) with `sort(xs)`, a comparator `sort_by(xs, fun(a, b) -> int)`, or both.
- **Format specs**: Python-style `{x:>8.3}` in f-strings, or functions in `std.num` (`pad`, `fixed`).
- **Errors**: `Result<T, IoError>` with an enum of causes, or `Result<T, str>` as today.
- **File handles**: explicit `close`, a scoped `with_file(path, fun(r) { … })`, or `defer` (which the concurrency slice, [[MYLA-212]], wants for cleanup too).
- **Order**: the pure modules first (`std.str`, `std.char`, `std.sort`, `min`/`max`/`abs`, format specs), then I/O and processes.

## Recommendation

Decide [[MYLA-204]] first. Then the pure modules, written in Myla, which cost nothing per implementation (only new `__` primitives multiply by the implementations, see [[MYLA-201]]); `sort` with an `Ord` trait plus `sort_by`; format specs in f-strings; `Result<T, IoError>`; explicit `close` plus a scoped helper, `defer` decided with [[MYLA-212]]. Delete the duplicated helpers as each module lands.

## Decision

**D113 (2026-11-01): the recommendation.** Implementation: [[MYLA-189]] (pure modules, `Ord`, format specs), [[MYLA-190]] (I/O and processes), after [[MYLA-221]].

- [x] Decided, and recorded on [[Project/Decisions]]
- [x] The implementation tasks created or updated to match
