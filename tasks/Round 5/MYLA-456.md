---
id: MYLA-456
title: "A deadline's end and a cancel look through every timer"
type: improvement
status: backlog
priority: low
labels: [runtime, concurrency, round-5]
---
Found by [[MYLA-419]], whose M11 fix keeps a notifier wait's time limit at a known place among the timers. Two other paths of `lib/std/rt.my` still look through all of them, under the timers' lock: a task with a deadline (`task.timeout`) that ends before it takes its timer off with `timers_forget(fr | 1)`, which scans the heap; and `cancel_locked`, which every `task.cancel` and fired deadline runs (so every `task.first` and every `task.timeout` that runs out), scans every timer for its task's sleepers and heapifies, and walks the whole `__parked` list. With many timers set (32,000 `recv_timeout` receivers, say), a loop of `task.timeout` around short work costs O(timers) per call.

```myla
import std.task as task

async fun quick() -> int {
    return 1
}

async fun nap(ms: int) -> int {
    await task.sleep(ms)
    return 0
}

#main
async fun main() {
    // 20,000 sleepers keep the timers' heap big
    var fs: [async () -> int] = []
    for i in 0..20000 {
        fs.push(async () => await nap(2000))
    }
    async let sleepers = task.all(fs)
    await task.sleep(50)
    var n = 0
    for i in 0..20000 {
        if let Some(v) = await task.timeout(1000, async () => await quick()) {
            n += v
        }
    }
    print(n)
    let s = await sleepers
}
```

- [ ] A deadline's place among the timers kept where its task's end can find it (its cell, reachable from the task's first frame), as a waiter keeps its own (`timer_placed`)
- [ ] A cancel finding its task's sleepers and waiters without a scan (each task's own list, or a tag the firing timer checks)
