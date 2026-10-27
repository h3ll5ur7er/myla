---
id: MYLA-61
title: Actors and structured concurrency, Swift style
type: feature
status: backlog
priority: medium
labels: [concurrency, language, design]
---
A concurrency model close to Swift's: `actor` types whose state only their own methods touch, `async`/`await`, and tasks.

## What the Rust prototype taught

The removed [[Architecture/Rust-edition]] (git commit `043acb9`, `rust/docs/concurrency.md`) had a partial prototype that showed a surface syntax but not the guarantees:

- Syntax: `spawn expr` / `go expr` returned a task handle joined with `await`; `async fun` returned a handle; `await` on a non-task value was the identity. Channels: `make_chan()`, `send`, blocking `recv`, `try_recv`, and `select { x = ch => …, quit => … }`. `actor Counter { count: int  fun incr(var self) {…} }`, built with struct-literal syntax.
- Runtime: OS threads, unbounded crossbeam channels, a `std::sync::Mutex` per actor held for each method's whole body.
- What went wrong (formerly MYLA-40): a channel value held both ends, so it never closed and `recv()` with no sender left hung forever; spawned tasks nobody joined were killed when `main` returned (`spawn { print(..) }` printed nothing); an actor calling a method on itself deadlocked on its non-reentrant mutex; `async` on methods was ignored; actor fields couldn't be read from outside; bounded channels existed in the runtime but couldn't be created from Myla.

These are exactly the runtime failure modes the design below has to rule out in the checker.

Myla's value semantics are a good starting point: values crossing an actor boundary are copies, so most data is safe to send by construction.

## Goal: safety from the compiler, not the runtime

Like Swift's strict concurrency checking, the checker should reject unsafe programs instead of letting them deadlock or race at run time:

- **Isolation is static**: an actor's stored state is reachable only from its own methods. From outside, a call to an actor method is `await`ed (it may suspend); a synchronous access from outside is a type error.
- **No locks, no deadlocks**: an actor runs one message at a time on a serial executor, and an `await` inside an actor method suspends without holding anything, so calling yourself, or two actors calling each other, can't deadlock. The price is reentrancy: state may change across an `await`, which the checker can at least make visible (no references survive an `await`, because there are no references).
- **Send safety is a type property**: arguments and results crossing an actor boundary must be "sendable". Plain values (scalars, `str`, structs, enums, tuples, lists, maps of sendable values) are, because they're copied; the checker must decide about function values with captures and about reference-counted cells whose copies share storage (send a deep copy, or make those counts atomic).
- **Structured tasks**: child tasks can't outlive the scope that started them (task groups), so nothing is silently killed at the end of `main` (unlike the prototype).

## Open questions

- Isolation: does the checker prove that only an actor's methods reach its state, and what may be sent (Swift's `Sendable`)? Function values with captures and reference-counted cells shared between copies are the hard cases.
- Reference counting across threads: atomic counts everywhere, atomic only for values that cross actors, or one heap per actor with copying at the boundary?
- Runtime: a work-stealing scheduler over OS threads (`clone` without libc), or one thread per actor to start? Reentrancy rules for `await` inside an actor method (the Rust prototype deadlocked on self-calls).
- How `async` colours functions, and whether the interpreter and the native backend can share the semantics.

## Done when

- [ ] A design recorded as a decision on [[Project/Decisions]], prototyped in the Python toolchain's interpreter first (the semantics), then the native backend
- [ ] Examples and parity tests, including the deadlock and send-safety cases
