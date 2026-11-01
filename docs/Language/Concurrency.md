# Concurrency

> **D89 to D97, built** ([[MYLA-61]], [[MYLA-135]] to [[MYLA-150]]). Both checkers check what this page describes. The Python interpreter runs it with a thread per task, the self-hosted interpreter with tasks taking turns at each `await`. The self-hosted compiler builds every concurrent program (D91): its async functions as stackless state machines on heap frames, its tasks in parallel on a pool of OS threads, one per CPU unless the environment variable `MYLA_THREADS` says how many (at most 32; with `MYLA_THREADS=1` in the same order as the self-hosted interpreter's), its actors with executors of their own (D92, [[Architecture/Native-backend]]). The Python backend refuses concurrency. Suspension points are child tasks and actor calls: there is no `sleep`, timer or suspending I/O yet, so today's concurrency is parallel computation and actors.

Myla's concurrency follows Swift's: `async` functions that may suspend, `await` at every suspension, structured tasks that never outlive the scope that starts them, and `actor`s, whose state only their own methods touch. Tasks run in parallel on several threads. A value crossing into another task or actor is copied, so tasks share nothing but actors (D89).

[TOC]

## Async functions and `await`

```myla
async fun fetch(n: int) -> int {
    return n * 10
}

async fun twice(n: int) -> int {
    let a = await fetch(n)
    return a * 2
}
```

- `async fun` declares a function that may suspend. Calling it needs `await`, and only an async function (or a task) can `await`.
- `await` stands before the call, also inside an expression: `return await fetch(1) + await fetch(2)` awaits one after the other. A match guard can't await: bind the value before the `match`.
- A synchronous function can call synchronous ones only. There is no blocking wait for an async one.
- A function type can be async too: `async (int) -> int`; so can a lambda: `async (n: int) => await fetch(n)`. An async function value is called with `await` too. It isn't a synchronous one: `let f: (int) -> int = fetch` is an error.
- An async function can't be partially applied (`fetch(_)`) or composed with `>>`: either would make a synchronous function value of it.
- `#test` can't run an async function, `become` can't stand in one, and a trait's methods can't be async.

## Child tasks: `async let`

```myla
async fun total() -> int {
    async let a = fetch(1)
    async let b = fetch(2)
    return await a + await b
}
```

- `async let x = e` starts `e` as a child task, which runs in parallel with the rest of the function. Reading `x` awaits its result (`await x`), once. A call `e` makes needn't be awaited: the child task does that. `async let x: int = e` states the result's type.
- Only an async function has child tasks. A lambda in it can't await them (`a lambda can't await the child task 'a' of its function`).
- The scope that declared it waits for every child still running when it ends, even one never read: no task outlives its scope.
- A failure (a panic, a runtime error or `exit`) can't be caught, so a failure in any task ends the program at once (D97): every other task, the entry's too, stops at its next suspension point where it gives up its worker (waiting for a child, the turn after an awaited call, waiting for a busy actor), running no more of its body (D94). The failure is reported as soon as it happens, as if the entry had failed (a panic's message and place); the program ends, with status 1 or `exit`'s code, once no other task runs. It doesn't wait for the parent to `await` the failing child, so a parent waiting for another child, or a group of `task.all` waiting for its first function, doesn't wait for ever. If tasks fail at about the same time, the first one is reported. Since nothing catches a failure, a program that must survive one bad input has its children return a `Result` and decides what an error means. A task that loops without such an `await` isn't stopped: the failure is reported, but the program goes on until that task reaches a suspension point, for ever if it never does ([[MYLA-170]]). On one worker such a task, once it runs, keeps every other task from running, the failing one too.
- The child gets copies of what `e` uses, as a lambda does (D15, D48).
- `?` can't stand in an `async let`'s initializer (`'?' can't stand in an 'async let': its child task has no function to return from`): the child returns a `Result` and the parent applies `?` to what it awaits.

## A number of children: `std.task`

For a number of children known only at run time:

```myla
import std.task as task

async fun squares(n: int) -> [int] {
    var fs: [async () -> int] = []
    for i in 0..n {
        push(fs, async () => i * i)
    }
    return await task.all(fs)
}
```

- `task.all(fs)` runs each async function value of `fs` as a child task, all at once, and waits for every one of them.
- It gives the results in the order of `fs`, so the outcome doesn't depend on which finished first.
- It is written in Myla with `async let` alone ([[src/myla/std/task.my]]), so every implementation that runs `async let` runs it.

## Asking a child to stop: `task.cancel` and `task.cancelled`

Cancelling is cooperative (D96): `task.cancel(a)` asks the child task of `async let a` to stop, and the child decides where it can stop safely, by checking `task.cancelled()`:

```myla
import std.task as task

async fun worker(pool: Pool) -> str {
    let r = await pool.acquire()
    if task.cancelled() {
        await pool.release(r)
        return "stopped, gave back"
    }
    // ... use r ...
    await pool.release(r)
    return "finished"
}

async fun run(pool: Pool) -> str {
    async let w = worker(pool)
    task.cancel(w)
    return await w
}
```

- `task.cancel(a)` takes the name of an `async let` of this function (`task.cancel() takes the name of an 'async let'`); a lambda in it can't cancel it (`a lambda can't cancel the child task 'a' of its function`). It sets a flag and goes on: it doesn't wait, and the child isn't stopped. It can only be called: `let stop = task.cancel` is an error (D97 (4)), since the compiler takes the call itself.
- `task.cancelled()` is true in a task that was asked to stop, or whose parent (or theirs) was: a request reaches the whole tree below the child, its children started later too. Outside a task that was asked, and in a program without tasks, it is false.
- `await a` still gives what the child returned, and a scope still waits for its children: whatever the child does when asked, it runs to its end, so it can give back what it holds. Cancelling a child that has ended does nothing.
- The flag is the program's: unlike a failure (D97), it stops nothing at a suspension point.

## Actors

```myla
actor Counter {
    count: int
}

impl Counter {
    fun increment(var self) -> int {
        self.count = self.count + 1
        return self.count
    }

    fun get(self) -> int {
        return self.count
    }
}

async fun count_up(c: Counter, n: int) {
    for i in 0..n {
        let x = await c.increment()
    }
}

#main
async fun main() {
    let c = Counter { count: 0 }
    async let a = count_up(c, 1000)
    async let b = count_up(c, 1000)
    await a
    await b
    print(await c.get())        // 2000: one increment at a time
}
```

- `actor` declares a type like a struct, and `impl` gives it methods. Making one (`Counter { count: 0 }`) starts the actor and gives a **handle**. Copying the handle copies the reference: `let d = c` reaches the same actor. It is the only reference type in Myla.
- Its fields are reachable only through `self`, in its own methods. Outside them, `c.count` (read or assigned) and a pattern `Counter { count }` are errors. So is a lambda in its methods that captures `self`, as the lambda could run elsewhere.
- An actor can't have type parameters or attributes (no `#derive`), and can't implement a trait, whose methods are called without `await`.
- From outside, every method call is awaited (`await c.increment()`), also of a method declared without `async`; and the handle needn't be a `var` to call a `var self` method. The call runs on the actor, one call at a time, so its methods never race with each other. Its arguments go in, and its result comes out, as copies.
- Inside its methods, a call on `self` is an ordinary call (`self.get()`), since the actor is already running it, unless the method is `async`.
- An `async let` in an actor's method can't reach the actor's state through `self` (`an 'async let' can't reach the actor's state through 'self': its child task runs off the actor`): neither a field nor a synchronous method, since the child runs elsewhere while the actor runs other calls ([[MYLA-168]]). Read what the child needs into a `let` before the `async let`: the method reads it on the actor, and the child gets a copy. Passing `self` itself, the handle, or calling an `async` method of it is fine.
- An actor method may be `async`. While it waits, the actor runs other calls (it is *reentrant*), so two actors calling each other can't deadlock. Its fields may have changed when it resumes:
- In an async actor method, `await self.tally.bump()` with a `var self` method of a struct in a field works on a copy of the field, and the method's final `self` is written back to it when it returns, as for a list element (D99, [[MYLA-169]]). The actor's other calls run while it waits; a change they make to that field meanwhile is replaced by the write-back.

```myla
actor Account {
    balance: int
}

impl Account {
    async fun pay_out(var self, amount: int, audit: Auditor) -> bool {
        if self.balance < amount { return false }
        await audit.record(amount)      // other calls may run on this account here
        if self.balance < amount { return false }
        self.balance = self.balance - amount
        return true
    }
}
```

- The compiler warns when an actor's async method changes a field after an `await` on the strength of what it read before (D95): a field examined by a condition (`if`, `while`, a `match`'s scrutinee or guard, directly or through a local read from it) before an `await` and changed after it without being examined again, or set from a local read before an `await`. Without the second check above, `self.balance = self.balance - amount` gets `warning: 'self.balance' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile`, with a note at the `await`. Checking again after the `await`, or changing the field before it (reserving, and giving it back if need be), are the two ways out. The program is still built and run.

## What Myla guarantees, and what it doesn't

The concurrency stress tests ([[Development/Concurrency-stress-tests]], [[MYLA-144]], `tests/burn/test_concurrency_stress.py`) hold Myla to these answers, on every implementation and on 1 to 16 workers:

| Problem | In Myla |
| --- | --- |
| Shared mutation through aliases | Prevented: nothing mutable is shared but an actor, whose methods run one at a time; a lambda can't change what it captures (D93) |
| Check-then-act | One step in a synchronous actor method; across an `await` in an async one, a warning (D95) |
| An invariant over several objects | Holds when they live in one actor; across actors, no transaction keeps it (a limit) |
| Deadlock over resources | Prevented: no locks, reentrant actors whose executors never block a worker (D92) |
| Waiting cycles | Prevented: no channels, a task only awaits its own children and its earlier siblings |
| A failure while siblings run | It ends the program at once: every other task stops at its next suspension point, then the failure is reported (D94, D97), wherever its parent waits; a task looping without one isn't stopped |
| Cancellation and resource cleanup by the program | Cooperative: `task.cancel(a)` asks, the child checks `task.cancelled()` where it can stop and gives back what it holds, wherever it was asked (D96) |
| A stale result | The program's to decide (a request number, or cancelling the old request, which checks before publishing), as everywhere |
| Memory visibility | Prevented: values cross as copies, what an actor publishes is seen whole |
| Starvation | Actors serve the callers queued for them first in, first out; on several workers a caller that finds the actor busy with nobody queued waits a moment before queueing ([[MYLA-150]]), so two such callers get in in either order; a turn goes behind the others |

## What crosses: copies, and sendable values

An `async let`'s captures, a spawned child's captures and result, and an actor method's arguments and result are copied deeply when they cross (D89). Every value Myla has today can be copied this way: scalars, strings, lists, maps, structs, tuples, enums, function values (with their captures) and actor handles. So every value is *sendable*. The rule is for kinds of values that may come later.

A copy costs what the value holds: every element of a list, every entry of a map, all the way down. Natively it happens only in a program that has a task (frames mode, D92); passing a list of 100,000 integers to an actor's method costs about 1.5 ms a call there, where the same program without any `async let` passes it in place. Pass what the callee needs rather than a whole collection, or keep a large collection in the actor itself and send it the small changes ([[MYLA-173]]).

## The entry point

`#main async fun main()` runs as the first task. The program ends when it returns, and by then every task it started has ended too.

## Output from tasks running at once

The order between lines printed by tasks running at once isn't defined. Each `print` writes its line whole with one write, which a pipe keeps whole up to 4 KiB (`PIPE_BUF`): longer lines printed by tasks at the same moment can interleave ([[MYLA-173]]). A task that has long lines to print can return them for its parent to print in order. A program prints the same everywhere when its order comes from `await`: results joined in order, an actor's state read after its callers have finished.

## Errors

```myla
fun peek(c: Counter) -> int {
    return c.count              // 'count' belongs to the actor 'Counter': only its own methods reach it
}

fun bump(c: Counter) {
    c.increment()               // a call into the actor 'Counter' needs 'await'
}

fun later() -> int {
    return await fetch(1)       // 'await' can only stand in an async function
}

async fun forgot() -> int {
    return fetch(1)             // a call to the async function 'fetch' needs 'await'
}
```
