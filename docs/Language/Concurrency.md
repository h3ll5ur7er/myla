# Concurrency

> **D89, in progress.** Both checkers check what this page describes ([[MYLA-135]]). The Python interpreter runs it with a thread per task ([[MYLA-136]], `examples/concurrency.my`), the self-hosted interpreter with tasks taking turns at each `await` ([[MYLA-139]]). The self-hosted compiler builds every concurrent program ([[MYLA-138]], D91): its async functions as stackless state machines on heap frames, its tasks taking turns on one thread in the same order as the self-hosted interpreter's, its actors as handles to heap cells ([[Architecture/Native-backend]]); tasks run in parallel from [[MYLA-137]] on. The Python backend refuses concurrency.

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
- The child gets copies of what `e` uses, as a lambda does (D15, D48).

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
- An actor method may be `async`. While it waits, the actor runs other calls (it is *reentrant*), so two actors calling each other can't deadlock. Its fields may have changed when it resumes:

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

## What crosses: copies, and sendable values

An `async let`'s captures, a spawned child's captures and result, and an actor method's arguments and result are copied deeply when they cross (D89). Every value Myla has today can be copied this way: scalars, strings, lists, maps, structs, tuples, enums, function values (with their captures) and actor handles. So every value is *sendable*. The rule is for kinds of values that may come later.

## The entry point

`#main async fun main()` runs as the first task. The program ends when it returns, and by then every task it started has ended too.

## Output from tasks running at once

The order between lines printed by tasks running at once isn't defined. Each `print` writes its line whole. A program prints the same everywhere when its order comes from `await`: results joined in order, an actor's state read after its callers have finished.

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
