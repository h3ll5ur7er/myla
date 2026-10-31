---
id: MYLA-144
title: The concurrency stress tests
type: test
status: done
priority: medium
labels: [concurrency, tests, design]
---
After the actors' implementation ([[MYLA-135]] to [[MYLA-142]]): turn the language-neutral plan [[Development/Concurrency-stress-tests]] into Myla tests, to find out where Myla's design (D89: actors, structured tasks, deep copies, no shared mutable memory; D92: actor executors) prevents the classic concurrency failures and where it is a victim too. For each example, first record what Myla promises (compile-time rejection, runtime safety, a runtime error, or no guarantee); then write the program (a rejected one in `examples/errors/`, a runnable one in the concurrency tests on 1 to 16 workers, with a watchdog), and for each failure decide: a design change, a diagnostic, or a documented limit.

- [x] The guarantees table below, checked against the language and refined
- [x] The programs: rejected, runnable (all four implementations where they apply), on 1 to 16 workers
- [x] Each "victim" decided: design change (a decision), diagnostic, or documented limit
- [x] The Concurrency page says what Myla guarantees and what it doesn't

## First assessment (to verify)

| # | Test | Expected in Myla |
| --- | --- | --- |
| 1 | Shared mutation through hidden aliases | Prevented by design: captures are copies (D48), so each closure has a counter of its own; a shared counter must be an actor, whose methods are serialized, so the count is exact |
| 2 | Check-then-act | Safe inside one synchronous actor method (no suspension between check and act); with an `await` in between it is #6 |
| 3 | Write skew across objects | No transactions: an invariant over two actors can break; safe only when the state lives in one actor. A documented limit |
| 4 | Deadlock through resource ordering | No locks, and actors are reentrant with executors that never block a worker (D92): no deadlock; a transfer between two actors is not atomic (the total is right at the end, not between the two calls). Self-transfer: reentrancy makes it work |
| 5 | Deadlock without shared memory | No channels in the first version (D89); a child can't await its parent. Waiting cycles are hard to write; the runtime reports "every task waits for another one" when all workers idle |
| 6 | Reentrancy across an await | A likely victim: actors are reentrant (D89 (2)), so the stock can be checked before an `await` and decremented after another call did the same. Candidates: a diagnostic for actor state read before and written after a suspension, or a non-reentrant method kind |
| 7 | Cancellation during ownership transfer | No cancellation in the first version: not expressible yet; resource cleanup is by scope |
| 8 | Failure while siblings run | Structured: a scope waits for its children, so no local is reached after its scope. But without cancellation a sibling that loops forever keeps the failing scope waiting: a victim (a hang) |
| 9 | A stale result | Outside the language (application logic), as the plan says |
| 10 | Publication and memory visibility | No shared mutable memory between tasks: not expressible; values crossing are deep copies (D92) |
| 11 | Retryable transactions with side effects | No transactions: not applicable |
| 12 | Starvation under contention | Actor executors queue frames first in, first out; a yielding frame goes behind the others (MYLA-140): expected to make progress; measurable |

## Decisions so far

From the first runs (programs in `tests/burn/test_concurrency_stress.py` to come): test 1 → [[MYLA-145]] (D93, captures can't be changed: done); test 6 → [[MYLA-146]] (a diagnostic); test 8 → [[MYLA-147]] (cancellation); test 5's sibling await → [[MYLA-148]] (supported natively).

## Results

| # | Test | First run | Now |
| --- | --- | --- | --- |
| 1 | Hidden aliases | Callbacks changing a captured counter: no race, but 0 counted, and the implementations disagreed on the lambda's copy | Rejected at compile time (D93, [[MYLA-145]], error corpus); a shared counter is an actor: exactly 200,000 (`t01_shared_counter_actor`) |
| 2 | Check-then-act | One withdrawal, balance 20 | The same (`t02_check_then_act`) |
| 3 | Write skew | The invariant broke over two actors (every time on one worker) | A documented limit; the invariant kept in one actor holds (`t03_invariant_in_one_actor`) |
| 4 | Deadlock over resources | No deadlock, the total kept, a self-transfer leaves the balance | The same (`t04_transfers_both_ways`) |
| 5 | Waiting cycles | A cycle doesn't check; a child awaiting a sibling printed garbage natively | Supported everywhere ([[MYLA-148]], `t05_child_awaits_sibling`, `t05_siblings_share_a_result`) |
| 6 | Reentrancy across an await | The last item sold twice (stock -1) | A warning (D95, [[MYLA-146]]); checking again after the `await`: one sale (`t06_recheck_after_the_await`) |
| 7 | Cancellation and cleanup | Not expressible | Cooperative cancelling (D96, [[MYLA-149]]): cancelled at each of seven points, the worker gives back the resource, never twice (`t07_cancelled_holder_gives_back`) |
| 8 | Failure while siblings run | The interpreters hung, native code left the sibling running | The sibling cancelled, the failure ends the program, everywhere (D94, [[MYLA-147]], two `t08_` programs) |
| 9 | A stale result | "ca" shown | The program's to decide: a request number (`t09_latest_request_wins`), or cancelling the old request (`t09_cancel_the_stale_request`) |
| 10 | Memory visibility | 42 | The same (`t10_publication_through_an_actor`) |
| 11 | Retryable transactions | Not applicable (no transactions) | Not applicable |
| 12 | Starvation | Every worker and every single request done | The same (`t12_progress_under_contention`) |

The table is on the Concurrency page too ([[Language/Concurrency]]).
- Unit 621, integration 2, burn 808 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (6,107,397 bytes).
