"""Burn test: what a deadline's end and a cancel cost does not grow with the
timers and waits of other tasks (MYLA-456).

A task's deadline (`task.timeout`) keeps its place among the timers, so a
task that ends first takes it off in O(log timers); a cancel (`task.cancel`,
`task.first`, a deadline that fires) finds the sleepers and waiters of its
task and the tasks below it through the task's own record, where it looked
through every timer, heapified them, and walked every parked waiter. The
program below times 2,000 `task.timeout`s around quick work and 2,000
`task.first`s of a quick task and a sleeping one, beside 20,000 other
sleepers and 5,000 parked receivers, and without them. Before the fix:
135 µs against 4 µs a timeout, 1.4 ms against 30 µs a `first`.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, Program, native_build, run_argv, write_program

PROGRAM = r"""import std.task as task
from std.task import Channel
from std.process import args
import std.num as num
import std.time as time

async fun quick() -> int {
    return 1
}

async fun nap(ms: int) -> int {
    await task.sleep(ms)
    return 0
}

async fun sleepy() -> int {
    await task.sleep(100000)
    return 1
}

async fun receive(ch: Channel<int>) -> int {
    return match await ch.recv() {
        Some(v) => v
        None => 0
    }
}

#main
async fun main() {
    let a = args()
    let others = match num.parse_int(a[1]) { Some(v) => v as int, None => 0 }
    let rounds = match num.parse_int(a[2]) { Some(v) => v as int, None => 2000 }
    let ch: Channel<int> = task.unbounded()
    var fs: [async () -> int] = []
    for i in 0..others {
        fs.push(async () => await nap(60000))
    }
    for i in 0..others / 4 {
        fs.push(async () => await receive(ch))
    }
    async let held = task.all(fs)
    await task.sleep(50)
    let t0 = time.now_ns()
    var n = 0
    for i in 0..rounds {
        if let Some(v) = await task.timeout(1000, async () => await quick()) {
            n += v
        }
    }
    let t1 = time.now_ns()
    for i in 0..rounds {
        match await task.first([async () => await quick(), async () => await sleepy()]) {
            Some((k, v)) => { n += v }
            None => {}
        }
    }
    let t2 = time.now_ns()
    print(f"{n} {(t1 - t0) / 1000} {(t2 - t1) / 1000}")
    task.cancel(held)
    let s = await held
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TimerScaling(unittest.TestCase):
    def test_deadlines_and_cancels_beside_many_timers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, PROGRAM, "scaling.my")
            binary = os.path.join(tmp, "scaling")
            native_build(Program(path), binary)

            def timed(others: int) -> tuple[int, int]:
                argv, exe = run_argv(binary, binary, [str(others), "2000"])
                p = subprocess.run(argv, executable=exe, capture_output=True, text=True, timeout=120)
                self.assertEqual((p.stderr, p.returncode), ("", 0))
                n, timeouts, firsts = (int(w) for w in p.stdout.split())
                self.assertEqual(n, 4000)
                return timeouts, firsts

            # the best of three each: the machine may be shared
            alone = [min(x) for x in zip(*(timed(0) for _ in range(3)))]
            crowded = [min(x) for x in zip(*(timed(20000) for _ in range(3)))]
            for what, a, c in zip(["timeout", "first"], alone, crowded):
                with self.subTest(what=what):
                    # µs for 2,000: a few times as much at most (the heap is
                    # 15 deep, the caches colder), not 30 to 50 times
                    self.assertLess(c, 6 * a + 20000, f"{c} µs beside 25,000 waits, {a} µs alone")


if __name__ == "__main__":
    unittest.main()
