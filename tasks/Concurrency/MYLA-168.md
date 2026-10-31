---
id: MYLA-168
title: A child task of an actor method reads the actor's state off the actor
type: bug
status: todo
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

- [ ] Both checkers reject `self` (a field read, or a call of a sync method on `self`) in an `async let` initializer of an actor method, as they do for a lambda in it (`type_actor_child_reads_self.my` in the error corpus, same message in both)
- [ ] Alternatively settle whether the parent may evaluate the captured fields before the child starts (a decision); the rejection is the safe first step
- [ ] The program above as a stress program (`t13_child_of_an_actor_method.my`) once it is rejected, or as a parity program if evaluation in the parent is chosen
