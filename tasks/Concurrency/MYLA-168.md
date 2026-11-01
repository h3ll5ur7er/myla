---
id: MYLA-168
title: A child task of an actor method reads the actor's state off the actor
type: bug
status: review
priority: high
labels: [concurrency, checker, actors]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Both checkers accept an `async let` inside an actor method whose initializer reads `self`:

```myla
actor Store { xs: [int], gen: int }
impl Store {
    fun churn(var self) { if len(self.xs) > 200 { self.xs = [] }; push(self.xs, 1) }
    async fun peek(self) -> int {
        async let a = total(self.xs, self.xs, self.xs)   // accepted
        async let b = total(self.xs, self.xs, self.xs)
        return await a + await b
    }
}
```

The normalizer wraps the initializer in an async lambda capturing `self` ([[selfhost/anf.my]]), the lowering deep-copies every capture but actor handles ([[selfhost/lower.my]]), so the child evaluates `self.xs` on another worker, off the actor, while `churn` runs on it (the parent left the actor at `await a`). With two `churner` tasks and two `peeker` tasks: `MYLA_THREADS=1` prints `true`; `MYLA_THREADS=4` gives `runtime error: index out of bounds` in 5 of 5 runs; `MYLA_THREADS=8` crashes or hangs. The Python interpreter is safe by accident (`_actor_field` locks), the self-hosted interpreter is single-threaded. [[Language/Concurrency]] promises that an actor's fields are reachable only through `self` in its own methods: this breaks it natively.

- [x] Both checkers reject `self` (a field read, or a call of a sync method on `self`) in an `async let` initializer of an actor method, as they do for a lambda in it (`type_actor_child_reads_self.my` in the error corpus, same message in both)
- [ ] Alternatively settle whether the parent may evaluate the captured fields before the child starts (a decision); the rejection is the safe first step
- [x] The program above as a stress program (`t13_child_of_an_actor_method.my`) once it is rejected, or as a parity program if evaluation in the parent is chosen

## Evidence

- Both checkers: `an 'async let' can't reach the actor's state through 'self': its child task runs off the actor`, with `help: read what the child needs into a 'let' before the 'async let'`, for a field read and for a synchronous method of `self` (passing the handle, or an async method, stays allowed). Error corpus: `type_actor_child_reads_self.my`, `type_actor_child_calls_self.my`; the unit test that pinned the old behaviour now checks the rejection and the idiom.
- `t13_child_of_an_actor_method` (the review's churn-and-peek program with the idiom) prints `true` everywhere, on 1 to 16 workers; writing it found [[MYLA-198]] (native code borrowed `let xs = self.xs` across the `await`).
- Not done: the alternative of evaluating the reads in the parent (a decision; the rejection was the safe first step).
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
