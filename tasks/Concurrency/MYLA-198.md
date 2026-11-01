---
id: MYLA-198
title: An async actor method borrowed its own fields across an await
type: bug
status: review
priority: high
labels: [concurrency, lowering, memory]
---
Found while writing the stress program for [[MYLA-168]]. In native code, an async actor method that read a field of `self` into a `let`, walked it with `for`, or matched on it, borrowed the field without a reference of its own (MYLA-122's borrowing: a `let` of a part of a variable nothing writes while it lives). An actor's `self` is no such variable: at every `await` the actor is left, its other calls change the field (a `push` that grows the list, an assignment that frees the old one), and the borrowed copy dangled.

- [x] [[selfhost/lower.my]]: the `self` of an async actor method is never a fixed place (`shared_self`), so its `let`s and `for` loops hold references of their own; a `match` on a field of it owns its copy
- [x] Stress programs: `t13_child_of_an_actor_method` (the idiom [[MYLA-168]]'s error message recommends, `let xs = self.xs` before the `async let`) and `t13_actor_state_across_an_await` (a `for` and a `match` over fields of `self` with an `await` inside, beside two tasks changing them)

## Evidence

- Before: `t13_child_of_an_actor_method` printed `false` natively on 1 and 4 workers (the borrowed list's length read back as an address, e.g. `ta 2 tb 2 len 140233093941944`), `true` in both interpreters; `t13_actor_state_across_an_await` hung natively on 4 workers (2 of 2 runs killed after 20 s).
- After: both print `true` in both interpreters and natively, on 1 and 4 workers (3 runs each), and in the stress suite on 1, 4 and 16 workers.
- The interpreters copy and were never affected; the Python backend has no concurrency (D91).
