---
id: MYLA-136
title: Concurrency in the Python interpreter
type: feature
status: in-progress
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
