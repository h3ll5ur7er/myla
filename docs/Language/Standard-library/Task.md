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
