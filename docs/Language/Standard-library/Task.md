# std.task

Child tasks whose number is known only at run time, notifiers that park a task until another wakes it, and on them channels between tasks, worker pools and the first of several (D89, [[Language/Concurrency]], [[MYLA-387]], [[MYLA-351]]).

```myla
import std.task as task
from std.task import Channel

async fun produce(ch: Channel<int>, n: int) {
    for i in 1..n + 1 {
        let r = await ch.send(i)
    }
    await ch.close()
}

async fun total(ch: Channel<int>) -> int {
    var sum = 0
    while let Some(x) = await ch.recv() {
        sum += x
    }
    return sum
}

async fun nap(ms: int, name: str) -> str {
    await task.sleep(ms)
    return name
}

#main
async fun main() {
    let ch: Channel<int> = task.channel(4)
    async let p = produce(ch, 100)
    async let a = total(ch)
    async let b = total(ch)
    await p
    print(await a + await b)
    match await ch.send(1) {
        Ok(()) => print("sent"),
        Err(e) => print(f"{e}"),
    }

    let words = task.channel<str>(0)
    async let w = words.recv()
    let sent = await words.send("handed over")
    print((await w).unwrap_or("none"))

    let squares = await task.pool(3, [1, 2, 3, 4, 5], async (x: int) => x * x)
    print(squares.map((x) => f"{x}").join(" "))

    var fs: [async () -> str] = []
    fs.push(async () => await nap(10000, "slow"))
    fs.push(async () => await nap(1, "quick"))
    match await task.first(fs) {
        Some(w) => print(f"{w.1} won"),
        None => print("nobody"),
    }

    let empty: Channel<int> = task.unbounded()
    match await empty.recv_timeout(10) {
        Ok(x) => print(f"{x}"),
        Err(e) => print(f"{e}"),
    }
}
// output:
// 5050
// channel closed
// handed over
// 1 4 9 16 25
// quick won
// timed out
```

| Function | Result |
| --- | --- |
| `all<T>(fs: [async () -> T]) -> [T]` (async) | Runs each function of `fs` as a child task, all at once, and gives their results in the order of `fs` |
| `cancel(child)` | Asks the child task of the `async let` named `child` to stop (D96): sets a flag it and its children see, and goes on; the compiler takes the call itself |
| `cancelled() -> bool` | True when the running task, or a task above it, was asked to stop |
| `yield()` (async) | `await task.yield()` gives the other ready tasks a turn and goes on after them; a task stopped by a failure elsewhere stops there (D97, D107, [[MYLA-228]]) |
| `timeout<T>(ms: int, f: async () -> T) -> Option<T>` (async) | Runs `f` as a child task: `Some` of its result, or `None` when `ms` milliseconds passed first, the child then cancelled (its sleeps end) and awaited (D124) |
| `sleep(ms: int)` (async) | `await task.sleep(ms)`: the running task asleep for at least `ms` milliseconds (none for `ms <= 0`), the others running meanwhile (D124, [[MYLA-230]]); tasks whose time comes at once go on earliest first |
| `notifier() -> Notifier` | A new notifier ([below](#notifiers)) |
| `channel<T>(cap: int) -> Channel<T>` | A channel holding at most `cap` values; `cap` 0 (or less) makes a rendezvous ([below](#channels)) |
| `unbounded<T>() -> Channel<T>` | A channel holding any number of values |
| `pool<J, R>(n: int, jobs: [J], f: async (J) -> R) -> [R]` (async) | `f` of every job by `n` workers at once (at least 1, at most one a job), each taking the next job when it finished one: the results **in the order of `jobs`** |
| `workers<J, R>(n: int, jobs: Channel<J>, results: Channel<R>, f: async (J) -> R) -> int` (async) | `n` workers taking jobs from `jobs` until it is closed and drained, sending `f` of each to `results` **as they finish**; `results` is closed when the last one ends. The number of results sent |
| `first<T>(fs: [async () -> T]) -> Option<(int, T)>` (async) | Runs each function of `fs` as a child task, all at once: the index and the result of the one that finished first; the others are cancelled and awaited, their results dropped. `None` for no functions |

`all` is written in Myla with `async let` alone, halving the list until one function is left, so the tasks nest about log2(len(fs)) deep. Cancelling is cooperative: the child decides where to stop ([[Language/Concurrency]]).

## Notifiers

A task that waits for a condition another task makes true parks on a notifier until that task wakes it, costing no CPU meanwhile ([[MYLA-387]], [[Language/Concurrency#Waiting until woken]]).

| Function or method | Result |
| --- | --- |
| `notifier() -> Notifier` | A new notifier, with no permit and nobody waiting. A `Notifier` is a handle: a copy reaches the same notifier (`==` tells), so it can be passed to tasks and kept in an actor's fields |
| `n.notify_one()` | Wakes the task that has waited longest on `n`; with none waiting, leaves a permit for the next wait. Permits add up, one per call: every `notify_one` ends exactly one wait, so a wake before the wait isn't lost |
| `n.notify_all()` | Wakes every task waiting on `n` now, and leaves no permit |
| `n.wait() -> bool` (async) | Parks the running task until it is woken (true), at once if a permit is there; false when the task is asked to stop (D96), which ends the wait at once |
| `n.wait_timeout(ms: int) -> bool` (async) | `wait` for at most `ms` milliseconds: false when they passed first; with `ms <= 0`, whether a permit was there to take |
| `n.listen() -> Listener` | `n` from now on: `l.wait()` and `l.wait_timeout(ms)` also end at once (true) when a `notify_all` came after the `listen`, so a broadcast between looking at a condition and waiting isn't missed |

A wait may end while the condition is still false (another task took the value first): wait in a loop that looks again. A program whose every task waits on a notifier, with nobody left to wake one, ends with the runtime error `every task waits for another one`. Natively a notifier lives as long as the program; parking and waking take a lock shared by the executor's timers.

```myla
import std.task as task

async fun ping(mine: task.Notifier, theirs: task.Notifier, n: int) -> int {
    var turns = 0
    for i in 0..n {
        theirs.notify_one()
        if await mine.wait() { turns += 1 }
    }
    return turns
}

async fun pong(mine: task.Notifier, theirs: task.Notifier, n: int) -> int {
    var turns = 0
    for i in 0..n {
        if await mine.wait() { turns += 1 }
        theirs.notify_one()
    }
    return turns
}

#main
async fun main() {
    let a = task.notifier()
    let b = task.notifier()
    async let x = ping(a, b, 1000)
    async let y = pong(b, a, 1000)
    print(await x + await y)
}
// output:
// 2000
```

## Channels

A `Channel<T>` is a queue between tasks, the oldest value first, of any element type. `task.channel(cap)` makes one holding at most `cap` values, `task.unbounded()` one holding any number. Its element type comes from where it goes, `let ch: task.Channel<int> = task.channel(4)`, or from a type argument, `task.channel<int>(4)` (D169). With `cap` 0 it is a rendezvous: a value goes straight from a sender to a receiver, and `send` waits until one took it.

| Method of `Channel<T>` (all async) | Result |
| --- | --- |
| `ch.send(x: T) -> Result<(), ChannelError>` | Sends `x`, waiting while a bounded channel is full, and on a rendezvous until a receiver took it. `Err(Closed)` when the channel is closed (also while it waits), `Err(Cancelled)` when the task was asked to stop while it waited: either way `x` wasn't sent |
| `ch.recv() -> Option<T>` | The next value, waiting while the channel is empty. `None` once it is closed and every value sent was received, or when the task was asked to stop while it waited (`task.cancelled()` tells which) |
| `ch.try_send(x: T) -> Result<(), ChannelError>` | Sends `x` if there is room now: `Err(Full)`, `Err(Closed)`. A rendezvous has room when a receiver waits |
| `ch.try_recv() -> Result<T, ChannelError>` | The next value if there is one now (on a rendezvous, from a waiting sender): `Err(Empty)`, or `Err(Closed)` once closed and drained |
| `ch.send_timeout(x: T, ms: int) -> Result<(), ChannelError>` | `send`, giving up with `Err(TimedOut)` when `ms` milliseconds passed before `x` went in (on a rendezvous, before a receiver took it) |
| `ch.recv_timeout(ms: int) -> Result<T, ChannelError>` | `recv`, saying why there was no value: `Err(Closed)`, `Err(Cancelled)` or `Err(TimedOut)` |
| `ch.close()` | Later sends give `Err(Closed)`, and so do the sends waiting now; receivers get what is left, then `None`. Closing again does nothing |
| `ch.len() -> int` | How many values it holds now; a rendezvous none (a waiting sender keeps its value until a receiver takes it) |

- `ChannelError` is `Closed`, `Full`, `Empty`, `TimedOut` or `Cancelled`, with `message()` and `Format` (D168, the spec ignored). Sending on a closed channel is an error, not a failure: a producer may race with the close.
- A copy of a `Channel<T>` reaches the same channel, so tasks share one by passing it on. Values go in and come out as copies, as for any actor (D89): a list changed after it was sent stays as it was sent.
- **Exactly once.** Each step on the queue is one call of its actor, so a value is taken by one receiver only, and a `send` that gives up (closed, cancelled, timed out) didn't put its value in: a rendezvous, or a full channel, gives a waiting sender's value back when it stops waiting. The stress tests hold every value to one delivery with many producers and consumers, some cancelled in the middle, others timing out over and over ([[Development/Concurrency-stress-tests]], t31 to t33).
- **Cancelled while it waits.** A cancelled task's `recv` and `send` stop waiting at once, as its sleeps do (D124), but they take what is there: a value in the channel, or one handed to the receiver just as it stopped. So a loop that must stop checks `task.cancelled()` itself (`while !task.cancelled() { … }`).
- **A time limit.** `task.timeout(ms, f)` puts a limit on any await, a channel's too: `await task.timeout(50, async () => await ch.recv())` is `None` when nothing came in time. But a value that came just as the limit passed is dropped with the child's result, so for a channel prefer `recv_timeout` and `send_timeout`, which keep it.
- **Deadlock.** Channels can wait for each other: two tasks that both send first over two rendezvous channels wait for ever (the plan's example 5, `t05_channels_wait_for_each_other`). When every task of the program waits, it ends with `every task waits for another one` (`t34_channels_nobody_left`); a cycle among some tasks while others run isn't seen. A time limit is the program's way out ([[Language/Concurrency#What Myla guarantees, and what it doesn't]]).

### How a task waits

The queue is a generic actor ([[MYLA-386]]) holding the values and the tasks waiting for them, oldest first. A step that can go on at once is one call of it. One that can't registers its task in the same call, in a slot that has a notifier of its own, and the task parks on that notifier until the other side's step serves it: a send hands its value straight to the oldest waiting receiver; a receive moves the oldest waiting sender's value into the room it made, or on a rendezvous takes it; `close` ends every wait. The served task wakes and takes its outcome from the slot in one more call, which frees the slot. Looking and registering are one step, and so are serving and waking, so no wake is lost and nobody looks again and again.

A wait that ends without a wake (its time passed, or its task was asked to stop) still takes its outcome. Not served yet, the task is taken off, and a sender's value is given back. Served just before, it keeps what it was served with: a value handed to a receiver as it gave up is that receiver's, so it isn't left unseen while the other receivers sleep. The wake that came too late stays on the slot's notifier as a permit, which only ends a wait of the slot's next task early; that task finds it wasn't served and waits again. Slots and their notifiers are reused: a channel makes as many notifiers as it ever had tasks waiting at once.

Measured natively (x86-64, 4 cores), best of 5, 400,000 messages; the polling version is [[MYLA-351]]'s first attempt (32 turns, then sleeps of 1, 2 and 4 ms), measured on the same machine:

| Messages a second | 1 worker, parked | 1 worker, polling | 4 workers, parked | 4 workers, polling |
| --- | --- | --- | --- | --- |
| a channel of 16 between two tasks | 3.30 M | 3.09 M | 721,000 | 472,000 |
| a channel of 16, 8 producers and 8 consumers | 3.27 M | 3.13 M | 862,000 | 805,000 |
| a channel of 1 between two tasks | 3.26 M | 3.15 M | 566,000 | 361,000 |
| a channel of 256, 8 producers and 8 consumers | 3.27 M | 3.11 M | 968,000 | 771,000 |
| a rendezvous between two tasks | 1.87 M | 1.37 M | 365,000 | 106,000 |

Eight tasks waiting 2 s on empty channels take no measurable CPU (0 to 1 ms, on 1 and 4 workers), where looking again took 52 ms on one worker and 213 ms on four. A parked receiver wakes 3 µs after the send on one worker and about 15 µs on four (the median; polling: 1.3 to 2.2 ms, up to 4.2 ms). On four workers a message usually crosses cores, the woken task taken by another worker ([[MYLA-387]]).

## Worker pools

`task.pool(n, jobs, f)` runs `n` workers over a list of jobs: each takes the next job's index from a small actor when it finished one, so a slow job holds up one worker only, and the results come back in the order of `jobs`. Each worker gets a copy of `jobs` (D89). A worker waits for that actor as for any actor's call; nothing looks again. The pool doesn't look at `cancelled()` itself: when it is cancelled, `f` sees it and decides what to return, and the results stay one a job.

`task.workers(n, jobs, results, f)` runs `n` workers over a channel of jobs, until it is closed and drained, and sends each result to the channel `results` as it is finished, closing it when the last worker ends. It gives the number of results sent. Cancelled, a worker takes no further job: every job was then done once (its result sent) or is still in `jobs`. A result whose `send` gave up (`results` closed, or the task cancelled while `results` was full) is dropped and not counted; with `results` unbounded, none is.

## The first of several

`task.first(fs)` runs every function of `fs` as a child task and gives the index and the result of the one that finished first. Each sends its index to a channel when it has finished, and `first` waits on that channel, so it goes on as soon as the first one finished. It then cancels the others, as `task.timeout` cancels its child (their sleeps end, their channel waits give up), and awaits them before it returns, so no task outlives it; their results are dropped. Cancelled itself while it waits, it still waits for them all (they are cancelled too) and gives the one that finished first.
