---
id: MYLA-26
title: Partial application of a function returning an aggregate returns garbage
type: bug
status: done
priority: medium
labels: [selfhost, codegen, closures]
---
The partial-application thunk ([[selfhost/codegen.my]], around line 3174) passes no sret pointer and assumes scalar arguments. Partially applying a function that returns a struct prints `0 0` instead of the fields (for example `P{3,5}`).

## Done when

- [x] The thunk forwards the sret pointer and passes aggregate arguments by address, like `__fnval` adapters
- [x] Differential test with struct/tuple results and aggregate arguments

Also found: partial application of a **method** or a **function value** didn't link at all (the thunk called `myla_`). The thunk now handles all three targets: a method gets its receiver as the first filled argument; a function value is captured into the env and called through the closure convention. Filled aggregate arguments are copied into the env and owned like lambda captures. The self-hosted interpreter didn't support method partials either (it read the method as a field); fixed too.

Test: the parity program `partial_application_of_aggregates` (functions, a method, a lambda and a function-valued field; struct and tuple results, struct arguments filled and open). Before: the program crashed.
