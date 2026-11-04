"""The clock and `task.sleep` (D124, MYLA-230): natively on the executor's
timers, which an idle worker polls; in the self-hosted interpreter on the real
clock, or with MYLA_TIME=virtual on one that moves only when no task is ready.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT

# children asleep for 60, 20 and 40 ms wake in deadline order, the whole
# taking at least the longest
ORDER = """import std.task as task
import std.time as time

async fun nap(ms: int, name: str) -> int {
    await task.sleep(ms)
    print(name)
    return ms
}

#main
async fun main() {
    let start = time.now_ms()
    async let a = nap(60, "a")
    async let b = nap(20, "b")
    async let c = nap(40, "c")
    let total = await a + await b + await c
    let took = time.now_ms() - start
    print(total)
    print(took >= 60)
    print(took < 5000)
}
"""

# 200 tasks asleep for deadlines in a scrambled order, beside a task that
# computes; an actor records the order they woke in
MANY = """import std.task as task

actor Log {
    order: [int],
}

impl Log {
    fun add(var self, ms: int) {
        self.order.push(ms)
    }

    fun sorted(self) -> bool {
        var i = 1
        while i < self.order.len() {
            if self.order[i - 1] > self.order[i] { return false }
            i = i + 1
        }
        return true
    }

    fun count(self) -> int {
        return self.order.len()
    }
}

async fun nap(log: Log, ms: int) -> int {
    await task.sleep(ms)
    await log.add(ms)
    return 1
}

async fun busy() -> int {
    var x = 0
    for i in 0..20000 { x = (x + i) % 1003 }
    return x % 2
}

#main
async fun main() {
    let log = Log { order: [] }
    var fs: [async () -> int] = []
    for i in 0..200 {
        let ms = (i * 37) % 97 * 3
        fs.push(async () => await nap(log, ms))
    }
    async let spin = busy()
    let rs = await task.all(fs)
    let s = await spin
    var n = 0
    for r in rs { n = n + r }
    print(n + s - s)
    print(await log.count())
    print(await log.sorted())
}
"""

# a sleep of ten seconds, and sleeps of no time
LONG = """import std.task as task
import std.time as time

#main
async fun main() {
    let start = time.now_ms()
    await task.sleep(10000)
    await task.sleep(0)
    await task.sleep(-5)
    print(time.now_ms() - start >= 10000)
}
"""

# a task fails while a sibling sleeps for ten seconds: the program ends at once
FAILS = """import std.task as task

async fun long_nap() -> int {
    await task.sleep(10000)
    print("woke")
    return 1
}

async fun fails() -> int {
    await task.sleep(30)
    let xs = [1]
    return xs[3]
}

#main
async fun main() {
    async let a = long_nap()
    async let b = fails()
    print(await a + await b)
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Time(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, name: str, text: str) -> str:
        path = os.path.join(self.dir, name + ".my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def native(self, name: str, text: str) -> str:
        from ._tools import selfhost_tool
        path = self.source(name, text)
        asm = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT],
                             capture_output=True, text=True, check=True).stdout
        exe = os.path.join(self.dir, name)
        with open(exe + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm)
        subprocess.run(["gcc", "-nostdlib", "-static", "-o", exe, exe + ".s"], check=True)
        return exe

    def run_timed(self, cmd: list[str], **env: str) -> tuple[str, str, int, float]:
        start = time.monotonic()
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env={**os.environ, **env})
        return p.stdout, p.stderr, p.returncode, time.monotonic() - start

    def interpreted(self, name: str, text: str, **env: str) -> tuple[str, str, int, float]:
        from ._tools import selfhost_tool
        return self.run_timed([selfhost_tool("interp_main"), self.source(name, text), STDLIB_ROOT], **env)

    def test_sleepers_wake_in_deadline_order(self):
        want = "b\nc\na\n120\ntrue\ntrue\n"
        exe = self.native("order", ORDER)
        for workers in ["1", "4"]:
            for sched in ["", "fifo"]:
                with self.subTest(workers=workers, sched=sched):
                    out, err, code, _ = self.run_timed([exe], MYLA_THREADS=workers, MYLA_SCHED=sched)
                    self.assertEqual((out, err, code), (want, "", 0))
        for mode in ["", "virtual"]:
            with self.subTest(interpreter=mode):
                out, err, code, _ = self.interpreted("order", ORDER, MYLA_TIME=mode)
                self.assertEqual((out, err, code), (want, "", 0))

    def test_many_sleepers_beside_a_busy_task(self):
        # every sleeper wakes; with the virtual clock in deadline order exactly
        exe = self.native("many", MANY)
        for workers in ["1", "4"]:
            with self.subTest(workers=workers):
                out, err, code, _ = self.run_timed([exe], MYLA_THREADS=workers)
                self.assertEqual((out.splitlines()[:2], err, code), (["200", "200"], "", 0))
        out, err, code, _ = self.interpreted("many", MANY, MYLA_TIME="virtual")
        self.assertEqual((out, err, code), ("200\n200\ntrue\n", "", 0))

    def test_the_virtual_clock_takes_no_time(self):
        out, err, code, took = self.interpreted("long", LONG, MYLA_TIME="virtual")
        self.assertEqual((out, err, code), ("true\n", "", 0))
        self.assertLess(took, 5.0)

    def test_a_failure_does_not_wait_for_a_sleeper(self):
        exe = self.native("fails", FAILS)
        out, err, code, took = self.run_timed([exe], MYLA_THREADS="4")
        self.assertEqual((out, code), ("", 1))
        self.assertIn("runtime error: index out of bounds", err)
        self.assertLess(took, 5.0)
        out, err, code, took = self.interpreted("fails", FAILS)
        self.assertEqual((out, code), ("", 1))
        self.assertIn("runtime error:", err)
        self.assertLess(took, 5.0)


if __name__ == "__main__":
    unittest.main()
