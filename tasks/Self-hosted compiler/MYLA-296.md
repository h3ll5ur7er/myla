---
id: MYLA-296
title: "Natively, every worker's loop top takes the timer lock while any timer is armed"
type: improvement
status: backlog
priority: low
labels: [runtime, concurrency, performance]
---
> [!NOTE]
> Renamed on 2026-11-13 ([[MYLA-554]]): it was "The interpreter's memory per sleeping task", the half that is done (the first box). What is open is the native timer lock, the last box, so the title says that, and the task is back in `backlog`.

Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). 10,000 tasks sleeping at once take 2.5 s and 1.18 GB in the interpreter (about 115 KB per task) against 127 ms and 27 MB natively. Natively, with many workers, every loop top takes `__timer_lock` in `timers_fire` while any timer exists, a contention cost not yet measured.

- [x] Find what a suspended task keeps in the interpreter (its evaluator's frames? copies of the environment?) and shrink it; a test with 10,000 sleepers under a memory bound
- [x] Measure `timers_fire` on 16 workers with many timers (about 15 % slower with 1,000 sleepers armed, below)
- [ ] The loop top takes `__timer_lock` only when a timer is due: a word holding the earliest deadline, written under the lock wherever the heap changes and read with acquire at the loop top (a new runtime variable: a commit staging it in the seed first, D156); or a per-worker timer wheel, or one timer owner. Measured again on 16 workers, and the time and concurrency stress suites on every target

## Evidence

- What a task kept: its lambda. The interpreter's `eval_lambda` copied every variable of every scope into the closure, so each of the 10,000 `async () => await nap()` of a `task.all` kept the list being built, and every `fs.push` after one copied the list (copy on write): quadratic. A lambda now copies only the variables its body reads (`names_in_expr`/`names_in_block`, moved from the code generator, which captures by the same rule, into [[selfhost/ast.my]]). 10,000 sleepers through `task.all`: 600 MB and 1.76 s before, 29 MB and 0.70 s after (natively 21 MB and 0.07 s); a binary tree of 10,000 `async let` sleepers took 35 MB before and after.
- `test_ten_thousand_sleepers_in_the_interpreter` in `tests/burn/test_time.py`: the `task.all` program under 150 MB of peak RSS; 601 MB without the change, under the bound with it. `test_selfhost_interp`, `test_examples_run`, `test_examples_tests`, `test_concurrency_stress` and `test_compiler_parity` pass (207 tests).
- `timers_fire` measured: 64 CPU-bound tasks yielding 200 times each, with and without 1,000 two-second sleepers armed meanwhile, five runs each. On 1 worker no difference (2,051 against 2,028 ms, medians); on 16 workers 591 against 683 ms, about 15 % slower, as each loop top takes `__timer_lock` while any timer exists. Proposed (open): a word holding the earliest deadline, written under the lock wherever the heap changes, which the loop top reads with acquire to take the lock only when it is due. It is a new runtime variable, so it needs a commit staging it in the seed first.
