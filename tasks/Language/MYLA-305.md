---
id: MYLA-305
title: "Async test functions and cases (step 2 of MYLA-303)"
type: feature
status: done
priority: high
labels: [testing, concurrency, interpreter]
---
Step 2 of [[MYLA-303]] (D162, D116 amended): `#test` on an `async fun` runs the case as the entry task of a program of its own, every task it starts joined before the case ends, on the interpreter's one-worker order (D110); `#test(args)[expected]` on an async function with parameters by the same rule. An actor is tested through an async test function that makes it; an actor's method and an async method stay out.

- [x] The checker admits `#test` on async functions (not methods)
- [x] The interpreter runs an async case as the first task, its result the task's value, its failure the case's; the task state fresh for every case
- [x] A failed async case unwinds its deferred blocks too
- [x] The error corpus (`type_test_async.my` replaced by the async method's refusal), burn tests, docs

## Done (2026-11-07)

- The checker admits `#test` on async functions; an async method is refused with `'#test' can't run an async method (test it through an async test function, D162)` (`examples/errors/type_test_async.my`, repinned).
- The interpreter runs an async case through `run_as_first_task(fi, argv)` (what `run_async` became: the function as the first task, every task run, its result the task's value, a failure left as a synchronous call leaves one) after `reset_tasks()`, so every case is a program of its own; the async evaluator's `close_scope` unwinds a failing scope's deferred blocks under a case.
- Evidence: `test_test_functions.test_async_cases_run_as_the_entry_task`: an actor bumped by two children 200 times (`PASS  counts_in_parallel`), `#test(3)[6]` on an async function, a child's failure failing the case with the case's deferred block run (`      | case's defer`), an async case unwound, a case after a failed one seeing fresh state. Docs: [[Language/Attributes-and-testing#async-cases]], [[Language/Concurrency]].
