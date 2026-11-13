---
id: MYLA-576
title: "Native: every call of an actor's method from outside leaks 8 bytes"
type: bug
status: review
priority: medium
labels: [runtime, lowering, concurrency, native, leak, round-6]
---
Found by [[MYLA-549]] while chasing the last item of its list (`manyserve3.my` of the review's bundle: a program that starts an HTTP server and a client 12,000 times grows 555 bytes a round on one worker). The leak isn't std.http's: a built program's resident memory grows 8 bytes for each call of an actor's method from outside, whatever the method returns, on one worker and on four. A plain `async fun` called the same way doesn't grow. std.http's server makes an actor call per worker when it stops (`Tally.worker_ended`, 64 by default) and, with a request limit, two per request, which is the 555 bytes a round (64 × 8, and the server's own few) and the client's 32 bytes a round of two requests.

```myla
import std.fs as fs
from std.io import println

fun rss() -> str {
    return match fs.read_to_string("/proc/self/status") {
        Ok(s) => {
            var out = "?"
            for l in s.lines() { if l.starts_with("VmRSS") { out = l } }
            out
        }
        Err(e) => "?"
    }
}

actor Box {
    n: int,
}

impl Box {
    fun get(self) -> int {
        return self.n
    }
}

#main
async fun main() {
    let b = Box { n: 1 }
    println(f"before: {rss()}")
    for i in 0..1000000 {
        let v = await b.get()
    }
    println(f"after 10^6 calls: {rss()}")
}
```

`build/myla build` and run with `MYLA_THREADS=1`: `before: VmRSS: 76 kB`, `after 10^6 calls: VmRSS: 7904 kB` (with four workers 4,600 kB); a method without a result (`fun bump(var self) { self.n += 1 }`) the same. The same loop over `await plain(i)`, an `async fun` that returns `i`: 72 kB, then 84 kB. Base `6e699ca`.

- [x] Find what an actor call allocates and doesn't free (the call's frame or a record of `myla___actor_enter`'s queue, `lib/std/rt.my`, or the lowering of the call, `selfhost/lower.my`)
- [x] A burn test: 10^6 actor calls in a bounded resident size, natively, on aarch64 and wasm32
- [x] `manyserve3.my` (12,000 servers and clients) flat after the fix

## What it was

Nothing leaked: a worker's ready queue walked along its ring. Each worker's queue is a ring of `EXEC_CAP` (2^20) frame slots, 8 MiB, whose head and tail counters run either way ([[lib/std/rt.my]], `exec_push`, `push_oldest`, `exec_find`). A call of an actor's method from outside ends with a turn for the others (`yield_turn` after `leave_actor` in `actor_call`, [[selfhost/lower.my]]): the frame goes to the oldest end (head − 1) and the worker takes its newest (tail − 1), so with the queue otherwise empty both counters moved down a slot every call, and each call wrote the next 8 bytes of the ring. After 2^20 calls the whole ring was resident (7.9 MB; 1,000,000 calls 7,904 kB, 2,000,000 and 4,000,000 calls 8,272 kB: the plateau of the ring, which is why it looked like 8 bytes a call). A program without tasks (no executor work: the `args()`-less reproduction calls no task primitive) doesn't show it.

The fix, in `std.rt` only: a frame taken that empties its queue sets both counters back to 0 (`queue_took`, from `exec_find` and `exec_steal`, under the queue's lock), so a queue that drains reuses the start of its ring. A lock-free glance (`exec_peek`) can now read a head from before a reset beside a tail from after it and see an empty queue that has a frame; the sleeper's last glance comes after its acquire read of `__exec_seq`, and the push that made that frame bumps `__exec_seq` after it stores the tail, so the sleeper's `park` returns at once: no wake-up is lost (`exec_all_waiting` runs only while every worker is idle, when nothing is taken). The lowering is unchanged.

## Evidence

- The task's program (`MYLA_THREADS=1`, 10^6 calls): `before: VmRSS: 76 kB`, `after: 7904 kB` → after the fix 72 kB, then 88 kB; four workers 104 kB, then 132 kB. aarch64 (qemu, whose own RSS is 8.8 MB): 8,792 → 16,632 kB before, 8,800 → 8,832 kB after.
- `manyserve3.my` ([[MYLA-549]], 12,000 rounds, one worker): before 568 kB at round 10, 2,232, 3,896, 5,560, 7,224 kB at rounds 2,999 … 11,999; after 568, 572, 572, 572, 572 kB.
- The burn test `test_selfhost_codegen.SelfHostedCodegenParity.test_actor_calls_from_outside_run_in_bounded_memory`: 1,000 calls, then 999,000 more, the program reading its own `VmRSS` (a peak through the harness counts the Python parent's 10 MB from before the exec, which hid the plateau), on one worker and four, less than 1 MiB more. Before the fix: `7824 not less than 1024` (one worker) and `7780` (four) natively, `7908` and `6928` on aarch64; after: OK natively, on aarch64 and on wasm32 (where the ring is mapped in the linear memory from the start and `/proc` is Node's: the peak is bounded, 64 MB).
- Suites at the end: `scripts/test.sh fast` (886 tests) and `scripts/test.sh` (1,626 tests, 342 skipped): the one failure `test_embedded_std`, as expected until the integrator's seed; `scripts/test-target.py aarch64-linux` and `wasm32-wasi` for `test_stdio`, `test_net` and `test_term`; the platform modules' own cases on their targets (23, 23, 19), which first found `__on_raw_signal` named wrongly when std.platform is the entry (fixed, `platform_fn`).
