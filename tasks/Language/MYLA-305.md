---
id: MYLA-305
title: "Async test functions and cases (step 2 of MYLA-303)"
type: feature
status: in-progress
priority: high
labels: [testing, concurrency, interpreter]
---
Step 2 of [[MYLA-303]] (D162, D116 amended): `#test` on an `async fun` runs the case as the entry task of a program of its own, every task it starts joined before the case ends, on the interpreter's one-worker order (D110); `#test(args)[expected]` on an async function with parameters by the same rule. An actor is tested through an async test function that makes it; an actor's method and an async method stay out.

- [ ] The checker admits `#test` on async functions (not methods)
- [ ] The interpreter runs an async case as the first task, its result the task's value, its failure the case's; the task state fresh for every case
- [ ] A failed async case unwinds its deferred blocks too
- [ ] The error corpus (`type_test_async.my` replaced by the async method's refusal), burn tests, docs
