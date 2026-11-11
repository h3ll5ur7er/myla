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

- [x] A deadline's place among the timers kept where its task's end can find it (its cell, reachable from the task's first frame), as a waiter keeps its own (`timer_placed`)
- [x] A cancel finding its task's sleepers and waiters without a scan (each task's own list, or a tag the firing timer checks)

## What changed

- **A task's record.** A task that waits (asleep, parked on a notifier, watching a descriptor) or has a deadline gets a record when it first needs one, its pointer in its first frame's flags word above the flags (`rec << 4`; the flags are the bits 1 to 3, so no word of the frame header, which the three back ends lay out, changes). The record is linked under its parent's, made with it, so the records form the tree of the tasks below any that has one: `[parent][first child][next sibling][previous sibling][deadline's cell][wait][sleeper's place]`. `wait` is what the task waits on now, tagged (its frame asleep, its waiter parked, its frame watching): a task runs one frame at a time. `task_end` frees it under the timers' lock, which it now takes when the flags show a record or a deadline.
- **A deadline's end.** The deadline's cell is `[fired][place]`, its place kept by `timer_placed` (as a waiter keeps its time limit's since MYLA-419), and the record holds the cell: a task that ends first takes its deadline off with `timer_remove_at` in O(log timers) instead of `timers_forget`'s scan and heapify. A second deadline on one task (std.task never sets one) sets the flag 1 and is looked for as before.
- **A cancel** walks the records below its task (`cancel_locked`, `cancel_wait`): a sleeper's time is set to 0 and sifted up from the place its record keeps, a parked waiter is unparked and queued, a watching frame unwatched and queued. It looked at every timer (and heapified), every parked waiter (`__parked`, a list that goes: the runtime variable stays for its second word, the stuck report's claim) and every watch.

## Evidence

`tests/burn/test_timer_scaling.py` (new, in `_targets.SUITES`): 2,000 `task.timeout`s around quick work and 2,000 `task.first`s of a quick task and a sleeping one, beside 20,000 sleepers and 5,000 parked receivers and without them, the best of three; it fails when the crowded time is past six times the lone one plus 20 ms.

- Before (bccc624), natively: timeouts 5.3 and 7.6 ms alone, 175 and 216 ms crowded; `first`s 41 and 48 ms alone, 5.5 and 7.1 s crowded. The test failed: `4558059 not less than 262036` (µs, `first`).
- After: timeouts 8.1 and 8.7 ms alone, 12 and 17 ms crowded; `first`s 42 and 48 ms alone, 48 and 66 ms crowded. Passes natively, on aarch64 (qemu: 36 to 57 ms alone, 97 to 182 crowded for the timeouts) and on wasm32.
- The task's own program (20,000 sleepers, then 2,000 rounds): `timeout 270 ms first 2770 ms` before, `timeout 14 ms first 52 ms` after.
- Suites: `lib/std/task.my` 36/36 natively, aarch64 and wasm32; `net.my` 98/98, `process.my` 48/48, `io.my` 30/30 natively; `tests.burn.test_time`, `test_concurrency_stress`, `test_scheduling`, `test_net`, `test_process`, `test_task_yield` (50 tests OK), `test_selfhost_codegen` and `test_http` (53 OK). The bootstrap reaches its fixed point.
- Cost, sockets and HTTP (natively, interleaved with the base, the machine loaded by five other lanes, load 5 to 7 on 4 cores): 8 connections × 20,000 round trips of 16 bytes on 4 workers 8.2 to 9.8 s before, 8.2 to 11.9 s after (best 8.22 against 8.23); on one worker 6.65 to 7.92 s before, 6.61 to 8.16 after; one keep-alive client's 20,000 GETs 18,100 to 31,700 a second before, 13,200 to 26,500 after, four async clients 5,000 to 21,500 against 5,300 to 12,900: within the noise of the machine.
