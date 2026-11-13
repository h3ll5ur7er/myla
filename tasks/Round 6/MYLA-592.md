---
id: MYLA-592
title: "Native: a SIGSEGV sent by `kill` is swallowed once"
type: bug
status: todo
priority: low
labels: [runtime, native, signals, round-6]
---
Found by [[MYLA-548]] (the runtime lane of round 6) with the review's `t_raw.py`, beside D192. The stack overflow handler `__on_segv` ([[selfhost/runtime_x86.my]], `runtime_a64.my`) takes every SIGSEGV for a fault: one whose address isn't near a stack gets its default action back and returns, so that the fault happens again and kills the program. A SIGSEGV sent by another process (`kill -SEGV`, `si_code` SI_USER) faults nothing again, so the program goes on as if nothing came; only a second one kills it.

```myla
import std.task as task
from std.io import println

#main
async fun main() {
    println("ready")
    await task.sleep(3000)
    println("still running")
}
```

Built (`build/myla build`) and sent one `kill -SEGV` half a second in: `ready`, then `still running` and exit status 0, where a program dies of the signal (status -11, as a C program does). In raw mode the terminal then stays raw as well. Base `07445ab` and after MYLA-548.

- [ ] `__on_segv` tells a signal sent (`si_code` <= 0: SI_USER, SI_TKILL, SI_QUEUE) from a fault and ends the program as the signal would (the default back, the signal sent again), on x86-64 and aarch64
- [ ] A case that sends SIGSEGV to a sleeping program and expects it killed by it
