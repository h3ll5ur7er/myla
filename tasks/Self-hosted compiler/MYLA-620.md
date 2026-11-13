---
id: MYLA-620
title: "Interpreter: the entry's `exit` waits for a child that sleeps or waits for input, and reports one on a notifier as stuck"
type: bug
status: review
priority: low
labels: [interpreter, concurrency]
---
Found by round 6's follow-up interpreter lane while it measured [[MYLA-604]]: that task's program ends with `exit(0)` while 400 tasks wait for the standard input, and under `myla run` it ended only once the pipe closed. When the entry task fails or exits, its scope cancels its children (D94) with `cancel_task` ([[selfhost/interp.my]]), which marks them to stop "when they next run"; but a child asleep, waiting for a descriptor or parked on a notifier is on none of the ready lists, so it ran again only when its time came or its input did. Natively `exit` ends the program at once (D97).

```myla
import std.task as task
from std.io import stdin
from std.process import args, exit

async fun child(mode: str, n: task.Notifier) -> int {
    if mode == "sleep" {
        await task.sleep(60000)
    } else if mode == "input" {
        var r = stdin()
        let l = await r.read_line_async()
    } else {
        let woken = await n.wait()
    }
    print("child")
    return 1
}

#main
async fun main() {
    let n = task.notifier()
    async let a = child(args()[1], n)
    await task.yield()
    print("exit")
    exit(3)
}
```

With its standard input a pipe that stays open, natively each mode prints `exit` and ends at once with status 3. Interpreted, `sleep` ended after the 60 s, `input` only once the pipe closed, and `notifier` with `runtime error: every task waits for another one` and status 1.

- [x] A cancelled task that waits is made ready, as `task.cancel` makes it (`request_cancel`): out of its sleep, its descriptor's wait or its notifier's, so it stops at once
- [x] A test: the program above ends at once in each mode, with its output and status

## What was built

`cancel_task` and `request_cancel` share `wake_to_stop`, which takes a waiting task (state 1) off the sleepers (its time made now), the waits for a descriptor and the notifiers' waits (the wait cancelled), and makes it ready; the run loop then stops it as a cancelled task, as before.

## Evidence

- **Failing first.** `test_selfhost_interp…test_exit_ends_the_tasks_that_wait` against the base (aef0b21's `interp.my`): `sleep` and `input` killed after the test's 30 s, `notifier` `('exit\n', 'runtime error: every task waits for another one\n', 1)`; now each `('exit\n', '', 3)` in 0.01 to 0.02 s, as natively.
- The suites are [[MYLA-604]]'s (same commit).
