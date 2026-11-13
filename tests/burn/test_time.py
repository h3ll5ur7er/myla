"""The clock and `task.sleep` (D124, MYLA-230): natively on the executor's
timers, which an idle worker polls; in the self-hosted interpreter on the real
clock, or with MYLA_TIME=virtual on one that moves only when no task is ready.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
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


# `task.timeout`: a child done in time, one asleep past the deadline (its
# sleep ends at once), one computing until it sees it was cancelled, one whose
# own child sleeps (woken too)
TIMEOUT = """import std.task as task
import std.time as time

async fun quick() -> int {
    await task.sleep(10)
    return 7
}

async fun slow() -> int {
    await task.sleep(5000)
    return 8
}

async fun spins() -> int {
    var n = 0
    while !task.cancelled() {
        n = n + 1
        await task.yield()
    }
    return n
}

async fun deep_sleep() -> int {
    await task.sleep(5000)
    return 1
}

async fun nested() -> int {
    async let inner = deep_sleep()
    return await inner + 1
}

fun show(r: Option<int>) -> str {
    return match r {
        Some(v) => f"some {v}",
        None => "none",
    }
}

#main
async fun main() {
    let start = time.now_ms()
    print(show(await task.timeout(1000, async () => await quick())))
    print(show(await task.timeout(30, async () => await slow())))
    let r = await task.timeout(30, async () => await spins())
    print(show(r))
    print(show(await task.timeout(30, async () => await nested())))
    print(time.now_ms() - start < 4000)
}
"""

# 10,000 tasks asleep at once through `task.all` (MYLA-296)
TEN_THOUSAND = """import std.task as task

async fun nap() -> int {
    await task.sleep(50)
    return 1
}

#main
async fun main() {
    var fs: [async () -> int] = []
    for i in 0..10000 {
        fs.push(async () => await nap())
    }
    let rs = await task.all(fs)
    print(rs.len())
}
"""

# `task.cancel` ends a child's sleep at once
CANCEL = """import std.task as task
import std.time as time

async fun nap() -> int {
    await task.sleep(5000)
    if task.cancelled() { return 1 }
    return 0
}

#main
async fun main() {
    let start = time.now_ms()
    async let a = nap()
    task.cancel(a)
    print(await a)
    print(time.now_ms() - start < 4000)
}
"""


# a task reading lines that come slowly with `read_line_async`, beside one
# printing a tick every 40 ms: the ticks go on while the reader waits
READ = """import std.io as io
import std.task as task

async fun reader() -> int {
    var r = io.stdin()
    var n = 0
    while true {
        match await r.read_line_async() {
            Ok(Some(line)) => {
                print("line " + line)
                n = n + 1
            },
            Ok(None) => { return n },
            Err(e) => { return -1 },
        }
    }
    return n
}

async fun ticker() -> int {
    var ticks = 0
    for i in 0..10 {
        await task.sleep(40)
        ticks = ticks + 1
        print("t")
    }
    return ticks
}

#main
async fun main() {
    async let r = reader()
    async let t = ticker()
    let lines = await r
    let ticks = await t
    print(f"{lines} lines, {ticks} ticks")
}
"""

# the only task reading lines of a non-blocking standard input (S4)
NONBLOCKING = """import std.io as io

#main
async fun main() {
    var r = io.stdin()
    var k = 0
    while k < 3 {
        match await r.read_line_async() {
            Ok(Some(l)) => print(f"line '{l}'")
            Ok(None) => print("end")
            Err(e) => print(f"Err({e})")
        }
        k += 1
    }
}
"""

# two tasks reading lines from standard input at once: both wait for the one
# descriptor, and every line is read by one of them (the review of
# 2026-11-06, R5: the second watch replaced the first, which waited for ever)
TWO_READERS = """import std.io as io

async fun reader() -> int {
    var r = io.stdin()
    var n = 0
    while true {
        match await r.read_line_async() {
            Ok(Some(line)) => { n = n + 1 },
            Ok(None) => { return n },
            Err(e) => { return -100 },
        }
    }
    return n
}

#main
async fun main() {
    async let a = reader()
    async let b = reader()
    print(await a + await b)
}
"""

# a time limit around a read that gets no input in time; and standard input
# from a regular file, which the poller can't watch (always ready)
READ_TIMEOUT = """import std.io as io
from std.fs import IoError
import std.task as task
import std.time as time

async fun first_line() -> str {
    var r = io.stdin()
    return match await r.read_line_async() {
        Ok(Some(line)) => line,
        Ok(None) => "end",
        Err(e) => match e {
            IoError.Other(code) => f"error {code}",
            _ => "error",
        },
    }
}

#main
async fun main() {
    let start = time.now_ms()
    let got = await task.timeout(50, async () => await first_line())
    print(match got {
        Some(l) => l,
        None => "timed out",
    })
    print(time.now_ms() - start < 1500)
}
"""

# lines on standard output 150 ms apart
FEEDER = "import sys, time\nfor i in range(3):\n    time.sleep(0.15)\n    sys.stdout.write(f'{i}\\n'); sys.stdout.flush()\n"


# `process.run_async`: a child that sleeps, writes both streams and exits 3,
# beside a ticker (its ticks go on meanwhile); 200 KB on each stream at once
# (no deadlock between the pipes); a program that doesn't exist; a time
# limit around a child that would sleep five seconds (killed); `run` as before
PROCESS = """import std.process as process
from std.process import ExitStatus, SpawnError
import std.task as task
import std.time as time

fun text(bs: [uint8]) -> int {
    return bs.len()
}

async fun child() -> str {
    return match await process.run_async("/bin/sh", ["-c", "sleep 0.2; echo out; echo error >&2; exit 3"]) {
        Ok(o) => {
            let code = match o.status {
                ExitStatus.Exited(c) => c,
                ExitStatus.Signaled(s) => -s,
            }
            f"{text(o.stdout)} {text(o.stderr)} {code}"
        },
        Err(e) => "spawn failed",
    }
}

async fun big() -> str {
    return match await process.run_async("/bin/sh", ["-c", "head -c 200000 /dev/zero | tr '\\\\0' a; head -c 200000 /dev/zero | tr '\\\\0' b >&2"]) {
        Ok(o) => f"{text(o.stdout)} {text(o.stderr)}",
        Err(e) => "spawn failed",
    }
}

async fun ticker() -> int {
    var n = 0
    for i in 0..5 {
        await task.sleep(30)
        n = n + 1
        print("t")
    }
    return n
}

async fun missing() -> str {
    return match await process.run_async("/no/such/program", []) {
        Ok(o) => "ran",
        Err(e) => match e {
            SpawnError.NotFound => "not found",
            _ => "other error",
        },
    }
}

async fun slow() -> int {
    return match await process.run_async("/bin/sleep", ["5"]) {
        Ok(o) => 0,
        Err(e) => 1,
    }
}

#main
async fun main() {
    let start = time.now_ms()
    async let c = child()
    async let t = ticker()
    print(await c)
    print(await t)
    print(await big())
    print(await missing())
    // the timeout ends the 5-second child: timed from the timeout itself, so
    // the interpreter's speed on the 400 KB above doesn't count (its copy
    // is slow interpreted on a loaded machine)
    let before = time.now_ms()
    let r = await task.timeout(50, async () => await slow())
    print(match r { Some(v) => "finished", None => "timed out" })
    print(time.now_ms() - before < 3000)
    print(match process.run("/bin/sh", ["-c", "echo sync"]) { Ok(o) => text(o.stdout), Err(e) => -1 })
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

    def test_ten_thousand_sleepers_in_the_interpreter(self):
        # MYLA-296: a lambda copies only the variables it reads; it copied
        # every one in scope, so each of these 10,000 kept the list being
        # built and every push copied it (600 MB; now under 40 MB)
        from ._tools import selfhost_tool
        cmd = [selfhost_tool("interp_main"), self.source("ten_thousand", TEN_THOUSAND), STDLIB_ROOT]
        # through a minimal helper process: a child's peak RSS counts its
        # parent's at the fork, and this one's is large in a full run
        from .test_selfhost_codegen import _MEASURE
        p = subprocess.run([sys.executable, "-I", "-S", "-c", _MEASURE, *cmd], capture_output=True, text=True,
                           timeout=120)
        code, peak_kb = p.stderr.split()[-2:]
        self.assertEqual((p.stdout, int(code)), ("10000\n", 0))
        self.assertLess(int(peak_kb) / 1024, 150, f"{int(peak_kb) / 1024:.0f} MB")

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
        self.assertIn("runtime error: list index 3 out of bounds (len 1)", err)
        self.assertLess(took, 5.0)
        out, err, code, took = self.interpreted("fails", FAILS)
        self.assertEqual((out, code), ("", 1))
        self.assertIn("runtime error:", err)
        self.assertLess(took, 5.0)

    def test_a_timeout_cancels_the_child_and_ends_its_sleeps(self):
        want = "some 7\nnone\nnone\nnone\ntrue\n"
        exe = self.native("timeout", TIMEOUT)
        for workers in ["1", "4"]:
            with self.subTest(workers=workers):
                out, err, code, _ = self.run_timed([exe], MYLA_THREADS=workers)
                self.assertEqual((out, err, code), (want, "", 0))
        out, err, code, _ = self.interpreted("timeout", TIMEOUT)
        self.assertEqual((out, err, code), (want, "", 0))
        # with the virtual clock time passes only when every task sleeps, so
        # the child that computes until cancelled is left out
        spinless = TIMEOUT.replace("    let r = await task.timeout(30, async () => await spins())\n    print(show(r))\n", "")
        out, err, code, took = self.interpreted("timeout_v", spinless, MYLA_TIME="virtual")
        self.assertEqual((out, err, code), ("some 7\nnone\nnone\ntrue\n", "", 0))
        self.assertLess(took, 5.0)

    def test_cancelling_a_sleeping_child_wakes_it(self):
        exe = self.native("cancel", CANCEL)
        # ten times on 4 workers: a cancel between the child's look at its
        # flags and its timer let it sleep its whole time (MYLA-163, about one
        # run in 60 natively, one in 6 under qemu)
        for workers in ["1"] + ["4"] * 10:
            with self.subTest(workers=workers):
                out, err, code, _ = self.run_timed([exe], MYLA_THREADS=workers)
                self.assertEqual((out, err, code), ("1\ntrue\n", "", 0))
        out, err, code, _ = self.interpreted("cancel", CANCEL)
        self.assertEqual((out, err, code), ("1\ntrue\n", "", 0))

    def fed(self, cmd: list[str], feeder: str, **env: str) -> str:
        feed = subprocess.Popen([sys.executable, "-c", feeder], stdout=subprocess.PIPE)
        try:
            out = subprocess.run(cmd, stdin=feed.stdout, capture_output=True, text=True, timeout=60,
                                 env={**os.environ, **env}).stdout
        finally:
            feed.stdout.close()
            feed.wait()
        return out

    def fed_after_a_tick(self, cmd: list[str], **env: str) -> tuple[list[str], bool]:
        # The program's output lines, and whether it ticked within 30 s
        # while its reader waited. Its input is three lines 150 ms
        # apart, the first written only once the program printed a tick:
        # its reader, started before the ticker, is waiting by then, so the
        # tick came while a read was pending. A first line written 150 ms
        # after the start raced the program's own start under load
        # (MYLA-500).
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, env={**os.environ, **env})
        ticked = threading.Event()
        ended: list[bool] = []
        fed: list[bool] = []

        def feed() -> None:
            try:
                if ticked.wait(30) and not ended:
                    fed.append(True)
                    for i in range(3):
                        if i > 0:
                            time.sleep(0.15)
                        proc.stdin.write(f"{i}\n")
                        proc.stdin.flush()
                proc.stdin.close()
            except BrokenPipeError:
                pass

        feeder = threading.Thread(target=feed)
        feeder.start()
        watchdog = threading.Timer(60, proc.kill)
        watchdog.start()
        lines: list[str] = []
        try:
            for line in proc.stdout:
                lines.append(line.rstrip("\n"))
                if line == "t\n":
                    ticked.set()
            proc.wait()
        finally:
            watchdog.cancel()
            ended.append(True)
            ticked.set()
            feeder.join()
            proc.stdout.close()
        return lines, fed == [True]

    def test_an_async_read_lets_the_other_tasks_run(self):
        exe = self.native("read", READ)
        from ._tools import selfhost_tool
        for label, cmd, env in [("native", [exe], {"MYLA_THREADS": "1"}),
                                ("interpreter", [selfhost_tool("interp_main"), self.source("read", READ), STDLIB_ROOT], {})]:
            with self.subTest(runner=label):
                lines, ticked = self.fed_after_a_tick(cmd, **env)
                # a tick while the reader waited: the worker wasn't blocked
                self.assertTrue(ticked, f"no tick while the read was pending: {lines}")
                self.assertEqual(lines[:1], ["t"])
                self.assertEqual([l for l in lines if l.startswith("line")], ["line 0", "line 1", "line 2"])
                self.assertEqual(lines[-1], "3 lines, 10 ticks")

    def test_two_readers_of_one_descriptor(self):
        exe = self.native("two_readers", TWO_READERS)
        from ._tools import selfhost_tool
        interp = [selfhost_tool("interp_main"), self.source("two_readers", TWO_READERS), STDLIB_ROOT]
        for label, cmd, env in [("native 1", [exe], {"MYLA_THREADS": "1"}), ("native 4", [exe], {"MYLA_THREADS": "4"}),
                                ("interpreter", interp, {})]:
            with self.subTest(runner=label):
                self.assertEqual(self.fed(cmd, FEEDER, **env), "3\n")

    def test_a_time_limit_around_a_read(self):
        exe = self.native("read_timeout", READ_TIMEOUT)
        from ._tools import selfhost_tool
        interp = [selfhost_tool("interp_main"), self.source("read_timeout", READ_TIMEOUT), STDLIB_ROOT]
        late = "import sys, time\ntime.sleep(2)\nprint('late')\n"
        for label, cmd, env in [("native 1", [exe], {"MYLA_THREADS": "1"}), ("native 4", [exe], {"MYLA_THREADS": "4"}),
                                ("interpreter", interp, {})]:
            with self.subTest(runner=label):
                self.assertEqual(self.fed(cmd, late, **env), "timed out\ntrue\n")
        path = os.path.join(self.dir, "in.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("from file\n")
        for label, cmd in [("native", [exe]), ("interpreter", interp)]:
            with self.subTest(file=label), open(path, encoding="utf-8") as fh:
                out = subprocess.run(cmd, stdin=fh, capture_output=True, text=True, timeout=60).stdout
                self.assertEqual(out, "from file\ntrue\n")

    def test_a_non_blocking_input_read_by_the_only_task(self):
        # the 2026-11-10 review's S4: with no other task, `read_line_async` of
        # a non-blocking stdin gave `Other(11)` (EAGAIN) natively, where the
        # interpreter waited for the input; now the thread waits for it
        # (std.rt's `wait_alone`) on both runners
        exe = self.native("nonblocking", NONBLOCKING)
        from ._tools import selfhost_tool
        interp = [selfhost_tool("interp_main"), self.source("nonblocking", NONBLOCKING), STDLIB_ROOT]
        for label, cmd in [("native", [exe]), ("interpreter", interp)]:
            with self.subTest(runner=label):
                r, w = os.pipe()
                os.set_blocking(r, False)
                proc = subprocess.Popen(cmd, stdin=r, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                os.close(r)
                try:
                    time.sleep(0.3)
                    os.write(w, b"first line\nsec")
                    time.sleep(0.3)
                    os.write(w, b"ond line\n")
                except BrokenPipeError:
                    pass
                os.close(w)
                out, err = proc.communicate(timeout=60)
                self.assertEqual((out, err, proc.returncode),
                                 ("line 'first line'\nline 'second line'\nend\n", "", 0))

    def test_a_child_process_waited_for_without_blocking_the_worker(self):
        want = "t\nt\nt\nt\nt\n4 6 3\n5\n200000 200000\nnot found\ntimed out\ntrue\n5\n"
        exe = self.native("process", PROCESS)
        for workers in ["1", "4"]:
            with self.subTest(workers=workers):
                out, err, code, _ = self.run_timed([exe], MYLA_THREADS=workers)
                if workers == "1":
                    self.assertEqual((out, err, code), (want, "", 0))
                else:
                    self.assertEqual((sorted(out.splitlines()), err, code), (sorted(want.splitlines()), "", 0))
        out, err, code, _ = self.interpreted("process", PROCESS)
        self.assertEqual((out, err, code), (want, "", 0))

    def test_child_processes_waited_for_by_programs_running_at_once(self):
        # MYLA-275: with the machine busy, a worker leaving `exec_idle` to take
        # the last queued frame could look idle to another worker's check,
        # which then ended the program ("every task waits for another one");
        # under qemu about 1 run in 25 did, 8 at a time, so 64 runs nearly always
        want = sorted("t\nt\nt\nt\nt\n4 6 3\n5\n200000 200000\nnot found\ntimed out\ntrue\n5\n".splitlines())
        exe = self.native("process_many", PROCESS)
        env = {**os.environ, "MYLA_THREADS": "4"}
        for round_ in range(8):
            runs = [subprocess.Popen([exe], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                    for _ in range(8)]
            for p in runs:
                out, err = p.communicate(timeout=120)
                with self.subTest(round=round_):
                    self.assertEqual((sorted(out.splitlines()), err, p.returncode), (want, "", 0))


if __name__ == "__main__":
    unittest.main()
