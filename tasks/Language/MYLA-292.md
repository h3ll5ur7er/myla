---
id: MYLA-292
title: "Negative slice bounds: an error, or before the start"
type: improvement
status: review
priority: low
labels: [slices, decision]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). D142 says a plain negative index stays an error, but a negative *bound* of a slice means "before the start": `xs[1:-1]` is silently empty and `xs[:-1:-1]` is the whole list reversed, which is the `i - 1` at `i == 0` slip that `^` was adopted to catch. Nothing legitimate produces a negative bound.

- [x] A decision: a negative bound is a runtime error like a negative index (the recommendation), or the page says what it means
- [x] Both runners and every target agree; a test

## Done (2026-11-07)

- D154. The lowering checks each plain bound of a slice (`check`, kind `index`: `__trap_index` on every backend) and the interpreter does the same before the step, so `xs[1:-1]` is `index out of bounds` at the slice where it was an empty list. A bound counted from the end still clamps (`xs[^9:2]`). [[Language/Collections-and-strings]] and `std.slice`'s header say so.
- `test_slices.test_runtime_errors`: a negative stop, a negative start from a variable, and a string's negative bound, interpreted and natively; the main program's `xs[-3:2]` is `xs[^9:2]`.
