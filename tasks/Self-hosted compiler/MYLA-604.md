---
id: MYLA-604
title: "Interpreter: every turn of the scheduler polls every task that waits for a descriptor"
type: bug
status: review
priority: low
labels: [interpreter, performance, concurrency]
---
Found by round 6's leftovers lane ([[MYLA-546]]). `run_as_first_task` calls `wake_sleepers` before each turn, which calls `wake_readers`, which polls every task's descriptor in `Interp.fd_waits` (`fd_wait_over`, a system call each) and copies the list. With N tasks waiting for input, each `await` costs N polls: a busy interpreted server with many connections mid-request pays for all of them at every turn. Natively the reactor waits in epoll and a turn costs nothing per waiter.

```myla
// N tasks wait for input on the standard input (a pipe that stays empty);
// meanwhile one task takes 20,000 turns: how long they take
import std.task as task
import std.time as time
from std.io import stdin
from std.process import args, exit
from std.num import parse_int

async fun reader() -> int {
    var r = stdin()
    return match await r.read_line_async() {
        Ok(Some(l)) => l.len()
        _ => 0
    }
}

async fun spin() -> int {
    let t = time.now_ms()
    var i = 0
    while i < 20000 {
        await task.yield()
        i += 1
    }
    return (time.now_ms() - t) as int
}

#main
async fun main() {
    let n = match parse_int(args()[1]) { Some(v) => v as int, None => 0 }
    var fs: [async () -> int] = []
    for k in 0..n { fs.push(async () => await reader()) }
    async let all = task.all(fs)
    let ms = await spin()
    print(f"{n} waiting: 20,000 turns in {ms} ms")
    exit(0)
}
```

```
$ sleep 30 | myla run waiters.my 0      # 151 ms
$ sleep 30 | myla run waiters.my 100    # 752 ms
$ sleep 30 | myla run waiters.my 400    # 2,321 ms
$ sleep 30 | MYLA_THREADS=1 ./waiters 400   # 1 ms natively
```

- [x] A turn costs nothing per waiting task when none became ready: look at the waits at most once a millisecond (as `wake_parked` looks at the parked sockets, [[MYLA-546]]), or with one poll of all of them, without changing the order in which ready tasks run (the interpreter's order is native code's on one worker, D110)
- [x] A test: the program above with 400 waiters takes about what it takes with none

## What was built

While tasks are ready, `wake_readers` ([[selfhost/interp.my]]) looks at the waits for a descriptor (`Interp.fd_waits`) as `wake_parked` looks at the parked sockets: not before `fds_gap` has passed since the last look, the gap 32 times what that look took (`look_gap`, from 1 to 50 ms), so the polls are at most a 32nd of the time; a look that finds none ready copies no list. With no task ready (`wait_for_sleeper`) it looks at once, as before. The tasks a look finds ready are made ready in the order they began waiting, as before, and a wait is entered only when its descriptor isn't ready already, so the order of the ready tasks of a program whose input is there doesn't change (D110); what changes is how soon a task waiting for input that comes later runs while others are ready: within the gap: a millisecond with a few waiters, 32 times a look with many, a few milliseconds with hundreds (natively a busy worker glances at the poller every 64 turns).

Measuring it found [[MYLA-620]]: the program ends with `exit(0)` while the readers wait, and interpreted it ended only once the pipe closed (`sleep 30 |` hid it); fixed in the same commit.

## Evidence

- **Failing first.** `test_selfhost_interp…test_a_turn_costs_nothing_per_waiting_task` (the program above with 0 and with 400 waiters, the standard input an empty pipe kept open; 400 must take less than twice 0's time plus 100 ms) against the base (aef0b21's `interp.my`): fails; passes now.
- **The program above**, `myla run`, the time it prints, before → after (2026-11-13, at a load under 1): 0 waiting 54 → 55 ms, 100 waiting 382 → 65 ms, 400 waiting 1,426 → 85 ms (1,000 waiting: 131 ms after). What 400 waiters still cost is their start (`task.all` runs the 400 readers to their waits during the 20,000 turns), not the turns. Natively 22 to 25 ms whatever the number.
- The suites: [[MYLA-605]]'s evidence (the three tasks measured together).
