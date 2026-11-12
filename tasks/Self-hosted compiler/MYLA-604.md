---
id: MYLA-604
title: "Interpreter: every turn of the scheduler polls every task that waits for a descriptor"
type: bug
status: todo
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

- [ ] A turn costs nothing per waiting task when none became ready: look at the waits at most once a millisecond (as `wake_parked` looks at the parked sockets, [[MYLA-546]]), or with one poll of all of them, without changing the order in which ready tasks run (the interpreter's order is native code's on one worker, D110)
- [ ] A test: the program above with 400 waiters takes about what it takes with none
