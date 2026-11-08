# std.task

Child tasks whose number is known only at run time (D89, [[Language/Concurrency]]).

| Function | Result |
| --- | --- |
| `all<T>(fs: [async () -> T]) -> [T]` (async) | Runs each function of `fs` as a child task, all at once, and gives their results in the order of `fs` |
| `cancel(child)` | Asks the child task of the `async let` named `child` to stop (D96): sets a flag it and its children see, and goes on; the compiler takes the call itself |
| `cancelled() -> bool` | True when the running task, or a task above it, was asked to stop |
| `yield()` (async) | `await task.yield()` gives the other ready tasks a turn and goes on after them; a task stopped by a failure elsewhere stops there (D97, D107, [[MYLA-228]]) |
| `timeout<T>(ms: int, f: async () -> T) -> Option<T>` (async) | Runs `f` as a child task: `Some` of its result, or `None` when `ms` milliseconds passed first, the child then cancelled (its sleeps end) and awaited (D124) |
| `sleep(ms: int)` (async) | `await task.sleep(ms)`: the running task asleep for at least `ms` milliseconds (none for `ms <= 0`), the others running meanwhile (D124, [[MYLA-230]]); tasks whose time comes at once go on earliest first |

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
