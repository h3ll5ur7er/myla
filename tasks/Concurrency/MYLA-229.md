---
id: MYLA-229
title: "`defer`"
type: feature
status: backlog
priority: low
labels: [concurrency, language]
---
D107 ([[MYLA-212]]): a way to run cleanup when a scope ends, also on failure and when a task is stopped (D97); the file handles of the standard library ([[MYLA-211]]) want it too. Its semantics need a decision of their own, proposed to the owner first:

- [ ] A proposal: scope (block or function), order (last in, first out), what ends a scope (`return`, `?`, `break`, a failure, a stop at a suspension point), what a deferred block may contain (`await`? `return`?), and its interaction with `become` (D87)
- [ ] The owner's decision recorded; then the implementation in every runner, with tests for each way a scope ends
