# Concurrency

> **D89 to D97, built** ([[MYLA-61]], [[MYLA-135]] to [[MYLA-150]]). The checker checks what this page describes. The interpreter runs it with tasks taking turns at each `await` (the retired Python interpreter ran a thread per task). The compiler builds every concurrent program (D91): its async functions as stackless state machines on heap frames, its tasks in parallel on a pool of OS threads, one per CPU unless the environment variable `MYLA_THREADS` says how many (at most 32; with `MYLA_THREADS=1` in the same order as the self-hosted interpreter's, see [[#Order of tasks]]), its actors with executors of their own (D92, [[Architecture/Native-backend]]). Suspension points are child tasks, actor calls, `task.yield`, `task.sleep` and `task.timeout` (D124), a notifier's waits ([[MYLA-387]], [[#Waiting until woken]]), and natively the reads that suspend (`std.io`'s `read_line_async` and the other `*_async` reads, a process's output through `std.process.run_async`). Any number of tasks may wait on one descriptor: the poller watches it once and its input wakes them all, each reading what is there or waiting again ([[MYLA-230]]). A timer fires when a worker reaches the top of its loop: on one worker, a `task.sleep(5)` beside a task computing for 300 ms wakes after the 300 ms. On wasm32 one worker runs every task (D125 (4): `MYLA_THREADS` is ignored there, in the one-worker order) and input never suspends.

Myla's concurrency follows Swift's: `async` functions that may suspend, `await` at every suspension, structured tasks that never outlive the scope that starts them, and `actor`s, whose state only their own methods touch. Tasks run in parallel on several threads. A value crossing into another task or actor is copied, so tasks share nothing but actors (D89). How many workers a target has (one on wasm32), and whether input suspends a task there, is on [[Language/Targets]].

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
- `#test` on an async function runs the case as the entry task of a program of its own (D162, [[Language/Attributes-and-testing#async-cases]]); `become` can't stand in an async function, and a trait's methods can't be async.

## Child tasks: `async let`

```myla fragment
async fun total() -> int {
    async let a = fetch(1)
    async let b = fetch(2)
    return await a + await b
}
```

- `async let x = e` starts `e` as a child task, which runs in parallel with the rest of the function. Reading `x` awaits its result (`await x`), once. A call `e` makes needn't be awaited: the child task does that. `async let x: int = e` states the result's type.
- Only an async function has child tasks. A lambda in it can't await them (`a lambda can't await the child task 'a' of its function`).
- The scope that declared it waits for every child still running when it ends, even one never read: no task outlives its scope.
- A failure (a panic, a runtime error or `exit`) can't be caught, so a failure in any task ends the program at once (D97): every other task, the entry's too, stops at its next suspension point where it gives up its worker (waiting for a child, the turn after an awaited actor call or `await task.yield()`, waiting for a busy actor), running no more of its body (D94). The failure is reported as soon as it happens, as if the entry had failed (a panic's message and place); the program ends, with status 1 or `exit`'s code, once no other task runs. It doesn't wait for the parent to `await` the failing child, so a parent waiting for another child, or a group of `task.all` waiting for its first function, doesn't wait for ever. If tasks fail at about the same time, the first one is reported. Since nothing catches a failure, a program that must survive one bad input has its children return a `Result` and decides what an error means. A task that loops without such an `await` isn't stopped: the failure is reported, but the program goes on until that task reaches a suspension point, for ever if it never does ([[MYLA-170]]). On one worker such a task, once it runs, keeps every other task from running, the failing one too. A loop that may run long gives the others a turn with `await task.yield()` ([[MYLA-228]]): the failure then ends the program at its next round.
- The child gets copies of what `e` uses, as a lambda does (D15, D48).
- `?` can't stand in an `async let`'s initializer (`'?' can't stand in an 'async let': its child task has no function to return from`): the child returns a `Result` and the parent applies `?` to what it awaits.

## A number of children: `std.task`

For a number of children known only at run time:

```myla
import std.task as task

async fun squares(n: int) -> [int] {
    var fs: [async () -> int] = []
    for i in 0..n {
        fs.push(async () => i * i)
    }
    return await task.all(fs)
}
```

- `task.all(fs)` runs each async function value of `fs` as a child task, all at once, and waits for every one of them.
- It gives the results in the order of `fs`, so the outcome doesn't depend on which finished first.
- It is written in Myla with `async let` alone ([[lib/std/task.my]]), so every implementation that runs `async let` runs it.

For tasks that hand values to each other while they run, `std.task` has channels (`let ch: task.Channel<int> = task.channel(4)`, `await ch.send(x)`, `await ch.recv()`), worker pools (`task.pool`, `task.workers`) and `task.first`, the first of several to finish ([[Language/Standard-library/Task#Channels]], [[MYLA-351]]). A channel is a [generic actor](#generic-actors) whose waiting senders and receivers park on [notifiers](#waiting-until-woken).

## Asking a child to stop: `task.cancel` and `task.cancelled`

Cancelling is cooperative (D96): `task.cancel(a)` asks the child task of `async let a` to stop, and the child decides where it can stop safely, by checking `task.cancelled()`:

```myla fragment
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
- The flag is the program's: unlike a failure (D97), it stops nothing at a suspension point, with two exceptions: a cancelled task's `await task.sleep(ms)` ends at once, and so does a sleep it starts later (D124), so a child asleep when asked can look at the flag without waiting out its sleep; and so does its wait on a notifier, which gives `false` ([[#Waiting until woken]]).

### A time limit: `task.timeout`

`await task.timeout(ms, f)` runs the async function value `f` as a child task and gives `Some` of its result, or `None` when `ms` milliseconds passed first (D124). At that moment the child is cancelled as `task.cancel` does it (its sleeps end), and `timeout` awaits it before it returns either way: the time limit is a request too, so a child that computes without looking at `task.cancelled()` keeps `timeout` waiting. Natively the limit is a deadline on the executor's timers, taken off when the child ends first, and not set at all when the child ended before `timeout` came to set it (on another worker); with `MYLA_TIME=virtual` the interpreter's clock moves only when every task sleeps, so a child that computes without sleeping never reaches its limit there.

## Waiting until woken

A task that waits for something another task does (a value put in a queue, a slot given back, a turn) parks on a **notifier** until that task wakes it ([[MYLA-387]], [[Language/Standard-library/Task#Notifiers]]). A parked task costs nothing: eight tasks parked for 2 s use no measurable CPU, where looking again every few milliseconds cost 240 ms on four workers, and it goes on as soon as it is woken.

```myla
import std.task as task

actor Box {
    value: int,
    waiting: [task.Notifier],
}

impl Box {
    // The value once it is set, or -1 with `me` kept to be woken: the look
    // and the registration are one call, so no wake can come between them
    fun take(var self, me: task.Notifier) -> int {
        if self.value >= 0 { return self.value }
        self.waiting.push(me)
        return -1
    }

    fun set(var self, v: int) {
        self.value = v
        for n in self.waiting { n.notify_one() }
        self.waiting = []
    }
}

async fun reader(b: Box) -> int {
    let me = task.notifier()
    while true {
        let v = await b.take(me)
        if v >= 0 { return v }
        let woken = await me.wait()
    }
    unreachable()
}

#main
async fun main() {
    let b = Box { value: -1, waiting: [] }
    async let r1 = reader(b)
    async let r2 = reader(b)
    await task.sleep(5)
    await b.set(42)
    print(await r1 + await r2)
}
// output:
// 84
```

- `task.notifier()` makes one. A `Notifier` is a handle, as an actor's is: a copy reaches the same notifier, so tasks share one by passing it on, and an actor's methods can keep the notifiers of the tasks waiting for it (above) and wake them.
- `n.notify_one()` wakes the task that has waited longest; when none waits, it leaves a **permit**, which the next wait takes and ends at once. Permits add up, one per `notify_one`, so a wake that comes before the wait (the reader above may be woken between `take` and `wait`) is never lost, and every `notify_one` ends exactly one wait.
- `n.notify_all()` wakes every task waiting now and leaves no permit. A task that looks at a condition and then waits for a broadcast takes `let l = n.listen()` before it looks and waits with `await l.wait()`, which ends at once if a `notify_all` came in between.
- `await n.wait()` gives `true` when the task was woken; `await n.wait_timeout(ms)` gives `false` when `ms` milliseconds passed first (and with `ms <= 0` doesn't wait: whether a permit was there). A wait may end while the condition is still false, another task having got there first: the waiter looks again, in a loop.
- A task asked to stop (D96) stops waiting at once, its wait giving `false`, and a wait it starts later doesn't wait; `task.cancelled()` tells it why. A failure elsewhere (D97) ends the program, and the tasks parked in it with it.
- A program whose every task waits, on notifiers or on each other, with no time limit, sleeper or input left to wake one, ends with the runtime error `every task waits for another one` (status 1), natively and in the interpreter. A cycle among some tasks while others go on isn't seen: it lasts as long as they do.
- Natively a notifier lives as long as the program, and parking and waking take the lock the executor's timers use. On one worker native code wakes tasks in the interpreter's order, so a program prints the same in both in every `MYLA_SCHED` order.

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
// output:
// 2000
```

- `actor` declares a type like a struct, and `impl` gives it methods. Making one (`Counter { count: 0 }`) starts the actor and gives a **handle**. Copying the handle copies the reference: `let d = c` reaches the same actor. It is the only reference type in Myla.
- Its fields are reachable only through `self`, in its own methods. Outside them, `c.count` (read or assigned) and a pattern `Counter { count }` are errors. So is a lambda in its methods that captures `self`, as the lambda could run elsewhere.
- An actor can't have attributes (no `#derive`), and can't implement a trait, whose methods are called without `await`. It may have type parameters ([generic actors](#generic-actors)).
- From outside, every method call is awaited (`await c.increment()`), also of a method declared without `async`; and the handle needn't be a `var` to call a `var self` method. The call runs on the actor, one call at a time, so its methods never race with each other. Its arguments go in, and its result comes out, as copies.
- Inside its methods, a call on `self` is an ordinary call (`self.get()`), since the actor is already running it, unless the method is `async`.
- An `async let` in an actor's method can't reach the actor's state through `self` (`an 'async let' can't reach the actor's state through 'self': its child task runs off the actor`): neither a field nor a synchronous method, since the child runs elsewhere while the actor runs other calls ([[MYLA-168]]). Read what the child needs into a `let` before the `async let`: the method reads it on the actor, and the child gets a copy. Passing `self` itself, the handle, or calling an `async` method of it is fine.
- An actor method may be `async`. While it waits, the actor runs other calls (it is *reentrant*), so two actors calling each other can't deadlock. Its fields may have changed when it resumes:
- In an async actor method, `await self.tally.bump()` with a `var self` method of a struct in a field works on a copy of the field, and the method's final `self` is written back to it when it returns, as for a list element (D99, [[MYLA-169]]). The actor's other calls run while it waits; a change they make to that field meanwhile is replaced by the write-back.

```myla fragment
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

- The compiler warns when an actor's async method changes a field after an `await` on the strength of what it read before (D95): a field examined by a condition (`if`, `while`, a `match`'s scrutinee or guard, directly or through a local read from it) before an `await` and changed after it without being examined again, or set from a local read before an `await`. Without the second check above, `self.balance = self.balance - amount` gets `warning[reentrancy]: 'self.balance' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile`, with a note at the `await`; `#allow(reentrancy)` on the method or its `impl` silences it where the program knows better (D161, [[Language/Attributes-and-testing#warnings-and-allow]]). The actor's own synchronous methods count ([[MYLA-171]]): a call `self.take()` changes every field `take` changes, through the methods it calls in turn, and a call `self.has_stock()` examines every field its body examines, so `if !self.has_stock() { … }` before the `await` and `self.take()` after it get the same warning. A field is changed by an assignment to it or to a part of it, and by a mutator called on it wherever the call stands, in a statement or inside an expression (`let x = self.items.pop()`, `return Some(self.counter.bump())`): the builtin `push`, `pop`, `remove` and `append`, or any `var self` method, std.list's `insert` and `sort` among them ([[MYLA-394]]). Checking again after the `await`, or changing the field before it (reserving, and giving it back if need be), are the two ways out. The program is still built and run. (The walk sees `self` and its methods only: a change made through another actor, or by an async method of the same actor, isn't followed.)

### Generic actors

An actor may have type parameters, as a struct may ([[MYLA-386]]): `actor Cell<T> { … }`, with its methods, synchronous or `async`, in `impl<T> Cell<T> { … }`, and those that need a bound in an impl of their own, `impl<T: Add> Cell<T>`.

```myla
actor Cell<T> {
    value: T,
    writes: int,
}

impl<T> Cell<T> {
    fun get(self) -> T {
        return self.value
    }

    fun put(var self, v: T) -> T {
        let old = self.value
        self.value = v
        self.writes += 1
        return old
    }
}

impl<T: Add> Cell<T> {
    fun add(var self, x: T) -> T {
        self.value = self.value + x
        self.writes += 1
        return self.value
    }
}

async fun fill(c: Cell<str>, n: int) -> int {
    for i in 0..n {
        let s = await c.add("ab")
    }
    return n
}

fun make<T>(v: T) -> Cell<T> {
    return Cell { value: v, writes: 0 }
}

#main
async fun main() {
    let n = Cell { value: 1, writes: 0 }        // a Cell<int>
    let s: Cell<str> = make("")
    async let a = fill(s, 3)
    async let b = fill(s, 2)
    print(await a + await b)
    print((await s.get()).len())
    print(await n.add(41))
    let old = await s.put("new")
    print(await s.get())
}
// output:
// 5
// 10
// 42
// new
```

- `Cell { value: 1, writes: 0 }` starts one, its type arguments inferred as a generic struct's are: from its fields, or from the expected type (`let s: Cell<str> = Cell { value: "", writes: 0 }`, a parameter's or a field's type, a generic function's result). One that nothing fixes is an error (`cannot infer type parameter(s) T; add a type annotation to guide inference`).
- Elsewhere its type names its arguments: `Cell<int>`, `[Cell<T>]`, a field `slot: Cell<T>` of a generic struct, `fun make<T>(v: T) -> Cell<T>`. Generic code passes, keeps and returns its handles like any other value, and every copy of a handle reaches the same actor.
- An impl covers every instance: `impl Cell<int>` is an error, as for a struct (`cannot 'impl' on a concrete generic instantiation`). A bounded impl's methods are there for the instances whose arguments meet the bound: `await t.add(false)` on a `Cell<bool>` is `type 'bool' does not satisfy the bound 'T: Add' required by 'Cell.add'`. A method may have type parameters of its own (`fun mapped<U>(self, f: (T) -> U) -> [U]`), and `T.zero()` works under `T: Zero` (D172).
- The rest is as for every actor: its fields, `T`s among them, are reached only through `self`; calls from outside are awaited and run one at a time per instance; arguments and results cross as deep copies, so a `T` that holds a list or a string is copied at the boundary and one of scalars costs nothing more; its async methods get the D95 warning (above), through its generic synchronous methods too.
- No rule limits the type arguments, since every value is sendable ([below](#what-crosses-copies-and-sendable-values)); an actor's handle is one too, so `Cell<Cell<int>>` and an actor that links to others of its own type, `actor Node<T> { v: T, next: Option<Node<T>> }`, are fine.
- Natively each instance has its own copy of the methods it calls and of its cell's layout and copies (`Cell.get__4.i32`, `Cell.get__4.str`, [[Architecture/Monomorphization]]); the interpreter runs one body for all, by erasure.

## What Myla guarantees, and what it doesn't

The concurrency stress tests ([[Development/Concurrency-stress-tests]], [[MYLA-144]], `tests/burn/test_concurrency_stress.py`) hold Myla to these answers, on every implementation and on 1 to 16 workers:

| Problem | In Myla |
| --- | --- |
| Shared mutation through aliases | Prevented: nothing mutable is shared but an actor, whose methods run one at a time; a lambda can't change what it captures (D93) |
| Check-then-act | One step in a synchronous actor method; across an `await` in an async one, a warning (D95) |
| An invariant over several objects | Holds when they live in one actor; across actors, no transaction keeps it (a limit) |
| Deadlock over resources | Prevented: no locks, reentrant actors whose executors never block a worker (D92); a task waiting on a channel or a notifier nobody will serve is the program's own (see the next row) |
| Waiting cycles | Prevented among tasks and actors: a task only awaits its own children and its earlier siblings. Through `std.task`'s channels and notifiers ([[#Waiting until woken]], [[Language/Standard-library/Task#Channels]]) a program can wait for ever: two tasks that both send first over two rendezvous channels wait for each other (`t05_channels_wait_for_each_other`). When every task waits, the program ends with `every task waits for another one`, while a cycle among some tasks lasts as long as the others run; a time limit (`send_timeout`, `recv_timeout`) is the program's way out |
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

## Order of tasks

Which ready task runs next isn't part of the language: a program whose result depends on it is wrong, and on several workers the order is whatever the timing makes it. What the runners do (D110, [[MYLA-231]]):

- A worker runs the newest ready task first, so a tree of tasks unfolds depth first and needs memory for its depth, not its width: `task.all` over 1.1 million functions on one worker took 20.8 s and 3.3 GB first in, first out, and takes 1.9 s and 354 MB depth first. An idle worker takes the oldest task of another worker's queue.
- An `async let` queues its child and the parent goes on; awaiting a child that has ended gives its result at once, and so does an awaited async function, method or function value that ends without suspending. An awaited actor call and `await task.yield()` give the other tasks a turn afterwards: the task goes behind every task ready then ([[MYLA-228]]).
- On one worker (`MYLA_THREADS=1`) native code runs tasks in the same order as the interpreter, so a program prints the same in both.
- A task asleep (`await task.sleep(ms)`, D124) goes on once its time has come, queued like a task that became ready then; sleepers whose time comes at once go on earliest first. Natively an idle worker waits in the platform's poll until the nearest deadline (the others park as before), so a program that never sleeps pays nothing; the interpreter waits for the earliest sleeper when no task is ready, on the real clock or, with `MYLA_TIME=virtual`, on one that jumps there.
- `MYLA_SCHED` changes the order, in the interpreter and in native code alike: `fifo` runs the oldest ready task first (breadth first, the order before D110), `seed:N` queues each ready task at the newest or the oldest end as a generator seeded with N decides, a turn still going behind the others. On one worker each order is reproducible and the same in both runners; the stress tests run every program in a few of them ([[Development/Concurrency-stress-tests]]).

## Output from tasks running at once

The order between lines printed by tasks running at once isn't defined. Each `print` writes its line whole with one write, which a pipe keeps whole up to 4 KiB (`PIPE_BUF`): longer lines printed by tasks at the same moment can interleave ([[MYLA-173]]). A task that has long lines to print can return them for its parent to print in order. A program prints the same everywhere when its order comes from `await`: results joined in order, an actor's state read after its callers have finished.

## Errors

```myla error
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
