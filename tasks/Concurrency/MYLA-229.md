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
- [x] The owner's decision recorded (D135); then the implementation in every runner, with tests for each way a scope ends

## Decided (2026-11-05): D135

The owner chose the recommendation, Swift's model:
- **Scope:** `defer { … }` is block-scoped, and the blocks run last registered first.
- **When it runs:** at the block's end, `return`, `?`, `break` and `continue`, and when the task is stopped at a suspension point. Not on a failure, which ends the program.
- **What the block may contain:** no `await`, `return`, `break` or `continue`.
- **With `become`:** a `become` runs the pending blocks before its call.

- [x] A proposal
