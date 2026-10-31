---
id: MYLA-136
title: Concurrency in the Python interpreter
type: feature
status: done
priority: medium
labels: [concurrency, interpreter]
---
D89 (6), after [[MYLA-135]]: the semantics, with each task on a Python thread, deep copies at every crossing, reentrant actors (a mailbox, one message at a time), structured scopes waiting for their children.

- [x] Tasks, `await`, `async let`, task groups (`std.task.all`, in Myla on `async let`)
- [x] Actors: handles, mailboxes (a lock taken by the calling thread: one call at a time), reentrancy (a waiting task lets go of its actor)
- [x] Deep copies at crossings (a child's variables and result, an actor method's arguments and result)
- [x] Examples whose output doesn't depend on the order of tasks running at once (`examples/concurrency.my`; the self-hosted interpreter and both backends leave it out until [[MYLA-137]] … [[MYLA-139]]). Parity programs follow with those tasks, since only the Python interpreter runs concurrency now.

## Groups: `task.all` instead of `task.group` and `spawn`

The draft page had `task.group(async (g: task.Group<T>) => { g.spawn(f) … await g.all() })`. A group changed through an immutable parameter needs a reference type with type parameters (an actor can't have them) and run-time primitives to start a task from a function value, in all four implementations. `task.all(fs: [async () -> T]) -> [T]` gives the same structured result (every child awaited, results in order) with `async let` alone: it halves the list until one function is left, so the tasks nest log2(n) deep. Its children start when `all` is called rather than at each `spawn`.

## Found on the way

- The Python loader didn't rename the names under an `await` (`await m.f()` across modules failed with "unknown name 'm'"); fixed, with a test (the self-hosted loader already did).

## Evidence

- `tests/unit/test_concurrency.py` (26 tests): async functions and values, `await` inside expressions, `async let` (results, awaiting twice, a scope waiting for children never awaited, in a loop body, copies of what a child uses, a child without a result, an awaited and an unawaited child's error, `exit` in a child), actors (a copied handle, copies in and out, calls on `self`, a reentrant call back into a waiting actor, two actors calling each other from two tasks 50 deep, a child task reading through `self`), `task.all` (order, none, children updating an actor) and a module function under `await`. They all failed on the interpreter's refusal before.
- The lock is what keeps an actor's calls apart: with the threads switching every microsecond, three tasks of 300 increments each give 900 every time; with the lock disabled, 360, 455 and 319. That run is a test now. The whole file passed 20 times in a row under frequent switching (no deadlock, no flaky result).
- `examples/concurrency.my` prints its expected output; the self-hosted checker agrees on it and its mutants.
- Unit 621, integration 2, burn 788 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,405,772 bytes).
