---
id: MYLA-61
title: Actors and structured concurrency, Swift style
type: feature
status: backlog
priority: medium
labels: [concurrency, language, design]
---
A concurrency model close to Swift's: `actor` types whose state only their own methods touch, `async`/`await`, and tasks. The [[Architecture/Rust-edition]] has a partial prototype (OS threads, a mutex per actor, unbounded channels) that shows the surface syntax but not the guarantees; its problems are in [[MYLA-40]].

Myla's value semantics are a good starting point: values crossing an actor boundary are copies, so most data is safe to send by construction.

## Open questions

- Isolation: does the checker prove that only an actor's methods reach its state, and what may be sent (Swift's `Sendable`)? Function values with captures and reference-counted cells shared between copies are the hard cases.
- Reference counting across threads: atomic counts everywhere, atomic only for values that cross actors, or one heap per actor with copying at the boundary?
- Runtime: a work-stealing scheduler over OS threads (`clone` without libc), or one thread per actor to start? Reentrancy rules for `await` inside an actor method (the Rust prototype deadlocks on self-calls).
- How `async` colours functions, and whether the interpreter and the native backend can share the semantics.

## Done when

- [ ] A design recorded as a decision on [[Project/Decisions]], prototyped in the Python toolchain's interpreter first (the semantics), then the native backend
- [ ] Examples and parity tests, including the deadlock and send-safety cases
