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

## Design options (D89, to decide)

The design is made in and for the toolchains we have: the Python interpreter (the semantics, first), the self-hosted interpreter, the Python backend and the self-hosted backend. Every implementation must print the same for every program, as today.

### 1. Execution model: how a task suspends

- **(a) Stackful (recommended).** Every task runs on a stack of its own (`mmap`ed, committed as it is touched, with a guard page). `await` switches stacks: it saves the callee-saved registers and `%rsp`, then picks the next task. Per D85 this needs nothing from the IR: no new instruction, frames stay where they are, and every function can suspend (the checker still requires `await` where a call may). In the Python interpreter, each task can be a Python thread handing over a baton (only one runs at a time), so the tree walker stays as it is. The self-hosted interpreter, once compiled with tasks, can run each interpreted task in a task of its own. Costs: a stack per task (64 KiB to 1 MiB reserved, only touched pages cost memory), and a deep recursion inside a task is bounded by that stack.
- **(b) Stackless (Swift's way).** Each `async` function is split into a state machine whose frame lives on the heap; `await` returns to the scheduler. Tasks are cheap, but this is D85's heaviest pressure point: slots in heap frames, split functions (`become` was the first step), and a second calling convention. Both interpreters would need generators or continuation passing.
- (a) can become (b) later without changing the language.

### 2. Threads

- **(a) One thread, cooperative, deterministic (recommended).** Tasks run one at a time; a task gives way only at an `await`. The order is part of the language: a FIFO run queue, a spawned task queued behind the running one. So every implementation prints the same, the parity tests keep working, there are no data races, and reference counts stay plain (D85's "one thread" holds). Blocking I/O blocks every task; an event loop over `poll` (`__poll` exists) is a later step.
- **(b) A multi-threaded executor.** Real parallelism, but output order is no longer defined, and reference counts must become atomic (or values crossing an actor must be copied deeply, or each actor needs a heap of its own). Better as a later decision, once the sendable rules of question 4 make it safe.

### 3. Structured tasks: the surface

- **(a) `async let` and task groups (Swift; recommended).** `async let x = f()` starts a child task; reading `x` awaits it, and the scope awaits every child that is still running when it ends (no task outlives its scope, unlike the prototype). A group (`await group(fun(g) { g.spawn(...) })`, or a block form) runs a dynamic number of children and collects their results.
- **(b) An explicit `spawn` inside a `tasks { … }` block**, returning a handle that `await` joins; the block waits for every handle it spawned. Simpler to explain, a little more ceremony.
- No detached tasks and no channels in the first version: the prototype's failures came from those.

### 4. Isolation and sendability

- An `actor` is the one reference type: copying an actor value copies a handle to the same actor (state and mailbox). Its fields are reachable only from its own methods (`self`); from outside, every method call is `await`ed and runs on the actor, one message at a time.
- **Sendable**, checked where a value crosses into or out of an actor (arguments and results of its methods, captures of a spawned task): scalars, `str`, and lists, maps, structs, tuples and enums of sendable values, because Myla copies them; actor handles; a function value whose captures are all sendable (captures are immutable copies, D48). Not sendable: nothing else exists yet, so the rule mostly guards the future (a multi-threaded executor, references).
- **Reentrancy (recommended: reentrant, as Swift).** An actor method that `await`s doesn't hold the actor: other messages may run in between, so calling yourself, or two actors calling each other, can't deadlock. The price: the actor's state may change across an `await`, which the language documents. Non-reentrant actors (a method holds the actor until it returns) keep state stable but deadlock on cycles, which a checker can't rule out in general.

### 5. `async` and the entry point

- `async fun` marks a function that may suspend; calling one requires `await`, and only an async function (or a task) can `await`. A synchronous function can't call an async one (no blocking wait in the first version). An actor's methods are async from outside and sync among themselves on `self`.
- `#main async fun main()` (or a `main` that awaits) runs as the root task; the program ends when it does, and structured tasks guarantee nothing is left running.

### Order of work, once decided

D89 recorded with the Language pages; the Python interpreter (the semantics, with parity programs and the error corpus for isolation and sendability); the Python checker and the self-hosted checker; the self-hosted interpreter; the runtime's stacks and scheduler in both native backends.

## Open questions

- Isolation: does the checker prove that only an actor's methods reach its state, and what may be sent (Swift's `Sendable`)? Function values with captures and reference-counted cells shared between copies are the hard cases.
- Reference counting across threads: atomic counts everywhere, atomic only for values that cross actors, or one heap per actor with copying at the boundary?
- Runtime: see options 1 and 2 above. Reentrancy rules for `await` inside an actor method (the Rust prototype deadlocked on self-calls): see option 4.
- How `async` colours functions, and whether the interpreter and the native backend can share the semantics.

## Done when

- [ ] A design recorded as a decision on [[Project/Decisions]], prototyped in the Python toolchain's interpreter first (the semantics), then the native backend
- [ ] Examples and parity tests, including the deadlock and send-safety cases
