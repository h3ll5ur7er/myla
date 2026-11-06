---
id: MYLA-292
title: "Negative slice bounds: an error, or before the start"
type: improvement
status: backlog
priority: low
labels: [slices, decision]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). D142 says a plain negative index stays an error, but a negative *bound* of a slice means "before the start": `xs[1:-1]` is silently empty and `xs[:-1:-1]` is the whole list reversed, which is the `i - 1` at `i == 0` slip that `^` was adopted to catch. Nothing legitimate produces a negative bound.

- [ ] A decision: a negative bound is a runtime error like a negative index (the recommendation), or the page says what it means
- [ ] Both runners and every target agree; a test
