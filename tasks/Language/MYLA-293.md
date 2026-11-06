---
id: MYLA-293
title: "Defaults in messages: `become`'s word count and `#test`'s arity"
type: improvement
status: backlog
priority: low
labels: [diagnostics, defaults]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). Two messages don't mention the defaults the caller filled in: a 6-argument `become g(…)` to a function with two defaults says "passes 8 argument words, 2 of them on the stack"; a `#test` case that leaves a default out says "'#test' expects 2 argument(s), got 1" (a case gives every argument, as documented, but the message doesn't say so).

- [ ] Both messages name the defaults; a burn test for each
