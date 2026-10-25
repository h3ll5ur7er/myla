---
id: MYLA-26
title: Partial application of a function returning an aggregate returns garbage
type: bug
status: backlog
priority: medium
labels: [selfhost, codegen, closures]
---
The partial-application thunk ([[selfhost/codegen.my]], around line 3174) passes no sret pointer and assumes scalar arguments. Partially applying a function that returns a struct prints `0 0` instead of the fields (for example `P{3,5}`).

## Done when

- [ ] The thunk forwards the sret pointer and passes aggregate arguments by address, like `__fnval` adapters
- [ ] Differential test with struct/tuple results and aggregate arguments
