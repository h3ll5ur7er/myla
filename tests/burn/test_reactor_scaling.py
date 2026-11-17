"""Burn test: what waiting for a descriptor costs does not grow with the
frames waiting for other descriptors, and an event wakes one frame per
readiness, not every frame waiting for that descriptor (MYLA-518).

The reactor's watches are kept per descriptor (`lib/std/rt.my`'s
`__watches`), so adding, taking and finding a frame's watch cost O(1),
where each looked through every watch; and a descriptor ready wakes the
first frame waiting for it (to receive, and the first to send), the
descriptor armed again for the others, where every frame watching it was
woken and all but one watched again.

- `RoundTrips`: 1,000 round trips of 16 bytes on one connection, both
  sides in `read_async` and `write_async` on one worker, the best of five
  tries, alone and then beside 50,000 tasks waiting in `accept_async` on a
  listener nobody connects to. Before the fix: 109 to 125 ms alone, 259 to
  319 ms crowded; after: 3.9 ms both.
- `Accepts`: 200 connections made one at a time to a listener with 2,000
  tasks in `accept_async`, each taken by exactly one task, cost about the
  CPU time they cost beside 200 tasks. Before the fix: 0.49 against 0.165 s
  (0.07 against 0.05 after).
- `Closed`: a task waiting in `read_async` on a socket another task closes
  gets EBADF (it waited for good natively), and the next socket given the
  descriptor is watched afresh.
- `Lots`: the primitives of a lot (MYLA-468: sockets parked with no task,
  std.http's kept connections), natively and interpreted.
- `Readers`: 500 tasks read one pipe to its end (`read_to_end_async`), each
  woken in turn as the input comes and ends; every byte is read once and
  every task ends (on every target: wasm32's poller too).
- `BusyWorkers`: as many tasks as workers, each running frames of 20 ms, the
  first writing a byte after 200 ms to a socket a task waits on: the reader
  is woken within 200 ms on 1 and 2 workers (MYLA-755: a busy worker
  glances at the poller once a millisecond has passed). Before the fix:
  1,060 and 1,040 ms (a glance every 64 frames). And a ping-pong beside as
  many tasks that only yield (short turns) makes more than 5,000 round trips
  a second: a busy worker glances every 64 turns too (MYLA-794). With the
  millisecond alone: 499 a second.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, Program, native_build, run_argv, selfhost_run, write_program

# A lot's primitives (MYLA-468, std.http's parked connections) on both
# runners: sockets parked with deadlines and tags, two made readable in
# turn, then those whose deadline passed taken by the earliest, the rest,
# the lot closed.
LOTS = r"""import std.net as net
import std.task as task
from std.net import TcpListener, TcpStream

fun conn(l: TcpListener, port: int) -> (TcpStream, TcpStream) {
    let a = match net.connect(net.addr(net.loopback(), port)) { Ok(s) => s, Err(e) => { panic("connect") } }
    let b = match l.accept() { Ok(s) => s, Err(e) => { panic("accept") } }
    return (a, b)
}

#allow(primitive)
#main
async fun main() {
    let l = match net.listen(net.addr(net.loopback(), 0)) { Ok(l) => l, Err(e) => { panic("listen") } }
    let port = match l.local_addr() { Ok(a) => a.port, Err(e) => 0 }
    let n = task.notifier()
    let lot = __sock_lot(n.id)
    var cs: [(TcpStream, TcpStream)] = []
    for i in 0..4 { cs.push(conn(l, port)) }
    // parked with deadlines 300, 100, -1, 200 and tags 10..13
    let ds = [300i64, 100i64, -1i64, 200i64]
    for i in 0..4 {
        print(__sock_park(lot, cs[i].1.handle, ds[i], 10i64 + i as int64))
    }
    print(__sock_ready(lot))
    // the third and the first get bytes
    for k in [2, 0] {
        var w = cs[k].0
        let x = w.write([7u8])
        let woke = await n.wait()
        let h = __sock_ready(lot)
        var which = -1
        for i in 0..4 { if cs[i].1.handle == h { which = i } }
        print(f"ready {which} tag {__sock_tag(h)}")
    }
    print(__sock_ready(lot))
    // by deadline: 1 (100) then 3 (200); none at 150 after the first
    print(__sock_expired(lot, 50) == 0)
    print(__sock_expired(lot, 150) == cs[1].1.handle)
    print(__sock_expired(lot, 150))
    // the rest
    print(__sock_expired(lot, -1) == cs[3].1.handle)
    print(__sock_expired(lot, -1))
    print(__sock_lot_close(lot))
    print(__sock_ready(lot))
}
"""

LOTS_OUT = """1
2
3
4
0
ready 2 tag 12
ready 0 tag 10
0
true
true
0
true
0
0
-1
"""

PROGRAM = r"""import std.io as io
import std.net as net
import std.task as task
from std.net import TcpListener, TcpStream
from std.task import Channel
from std.process import args
import std.num as num
import std.time as time

fun listener() -> TcpListener {
    return match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic(f"listen: {e}") }
    }
}

fun port_of(l: TcpListener) -> int {
    return match l.local_addr() { Ok(a) => a.port, Err(e) => 0 }
}

fun connected(port: int) -> TcpStream {
    return match net.connect(net.addr(net.loopback(), port)) {
        Ok(s) => s
        Err(e) => { panic(f"connect: {e}") }
    }
}

// One connection accepted, told on `ch`, closed: 1 (0 when cancelled).
async fun take(l: TcpListener, ch: Channel<int>) -> int {
    match await l.accept_async() {
        Ok(s) => {
            var c = s
            let sent = await ch.send(1)
            let gone = c.close()
            return 1
        }
        Err(e) => { return 0 }
    }
}

// Told on `ready` that it began, then as `take`.
async fun take_later(l: TcpListener, ready: Channel<int>, ch: Channel<int>) -> int {
    let sent = await ready.send(1)
    return await take(l, ch)
}

// `n` rounds of 16 bytes read and written back.
async fun echo(l: TcpListener, n: int) -> int {
    var c = match await l.accept_async() {
        Ok(s) => s
        Err(e) => { return 0 }
    }
    for k in 0..n {
        var got = 0
        while got < 16 {
            match await c.read_async(16 - got) {
                Ok(b) => { got += b.len() }
                Err(e) => { return k }
            }
        }
        let w = await c.write_async([1u8, 2u8, 3u8, 4u8, 5u8, 6u8, 7u8, 8u8, 9u8, 10u8, 11u8, 12u8, 13u8, 14u8, 15u8, 16u8])
    }
    let gone = c.close()
    return n
}

// The µs of `rounds` round trips of 16 bytes on `s` (`read_async` and
// `write_async`, as the other side's: each side waits for the other), the
// best of `times` tries.
async fun timed_rounds(s: TcpStream, rounds: int, times: int) -> int64 {
    var c = s
    var best: int64 = -1
    for t in 0..times {
        let t0 = time.now_ns()
        for r in 0..rounds {
            let w = await c.write_async([1u8, 2u8, 3u8, 4u8, 5u8, 6u8, 7u8, 8u8, 9u8, 10u8, 11u8, 12u8, 13u8, 14u8, 15u8, 16u8])
            var got = 0
            while got < 16 {
                match await c.read_async(16 - got) {
                    Ok(b) => { got += b.len() }
                    Err(e) => { panic(f"read: {e}") }
                }
            }
        }
        let took = (time.now_ns() - t0) / 1000
        if best < 0 || took < best {
            best = took
        }
    }
    return best
}

// The µs of 1,000 round trips alone, then beside `idle` tasks waiting to
// accept (the best of 5 tries each), in one line.
async fun round_trips(idle: int) -> str {
    let l = listener()
    async let e = echo(l, 10000)
    let c = connected(port_of(l))
    let alone = await timed_rounds(c, 1000, 5)
    let quiet = listener()
    let ch: Channel<int> = task.unbounded()
    let ready: Channel<int> = task.unbounded()
    var hs: [async () -> int] = []
    for i in 0..idle {
        hs.push(async () => await take_later(quiet, ready, ch))
    }
    async let idlers = task.all(hs)
    // every idle task begun, then a while for the last ones to wait (each
    // took O(waits) before the fix)
    for i in 0..idle {
        let r = await ready.recv()
    }
    await task.sleep(1000)
    let crowded = await timed_rounds(c, 1000, 5)
    if await e != 10000 {
        panic("echo")
    }
    task.cancel(idlers)
    var none = 0
    for g in await idlers {
        none += g
    }
    if none != 0 {
        panic("an idle task accepted")
    }
    return f"{alone} {crowded}"
}

// `waiting` tasks waiting to accept, `n` connections made one at a time,
// each awaited until a task took it and then a millisecond for the others
// to wait again; the rest cancelled: how many were taken.
async fun accepts(waiting: int, n: int) -> int {
    let l = listener()
    let port = port_of(l)
    let ch: Channel<int> = task.unbounded()
    var hs: [async () -> int] = []
    for i in 0..waiting {
        hs.push(async () => await take(l, ch))
    }
    async let takers = task.all(hs)
    await task.sleep(100)
    var cs: [TcpStream] = []
    for i in 0..n {
        cs.push(connected(port))
        let got = await ch.recv()
        await task.sleep(1)
    }
    task.cancel(takers)
    var k = 0
    for g in await takers {
        k += g
    }
    for s in cs {
        var x = s
        let gone = x.close()
    }
    return k
}

// What a read waiting on `s` gave.
async fun reader(s: TcpStream) -> str {
    var c = s
    return match await c.read_async(16) {
        Ok(b) => f"read {b.len()}"
        Err(e) => f"error {e}"
    }
}

// A task waiting in `read_async` on a socket another task closes, then
// one on the next connection (given the same descriptor): what each read
// gave.
async fun closed() -> str {
    let l = listener()
    let port = port_of(l)
    var a = connected(port)
    var b = match l.accept() { Ok(s) => s, Err(e) => { panic(f"accept: {e}") } }
    async let r = reader(b)
    await task.sleep(100)
    let gone = b.close()
    let first = await r
    var a2 = connected(port)
    var b2 = match l.accept() { Ok(s) => s, Err(e) => { panic(f"accept: {e}") } }
    async let r2 = reader(b2)
    await task.sleep(50)
    let w = a2.write([1u8, 2u8, 3u8])
    return f"{first}, {await r2}"
}

// The bytes `n` tasks read from the standard input to its end, each with a
// reader of its own.
async fun readers(n: int) -> int {
    var hs: [async () -> int] = []
    for i in 0..n {
        hs.push(async () => {
            var r = io.stdin()
            return match await r.read_to_end_async() {
                Ok(s) => s.len()
                Err(e) => -1000000
            }
        })
    }
    var total = 0
    for k in await task.all(hs) {
        total += k
    }
    return total
}

// `frames` frames of 20 ms, each a yield after it, so the worker that runs
// it stays busy; after frame `write_at` a byte written on `s`: when.
async fun busy_frames(s: TcpStream, frames: int, write_at: int) -> int64 {
    var c = s
    var wrote: int64 = 0
    for f in 0..frames {
        let end = time.now_ns() + 20000000
        while time.now_ns() < end {
        }
        if f == write_at {
            let w = c.write([1u8])
            wrote = time.now_ns()
        }
        await task.yield()
    }
    return wrote
}

// When a read waiting on `s` was woken.
async fun woken_at(s: TcpStream) -> int64 {
    var c = s
    return match await c.read_async(1) {
        Ok(b) => time.now_ns()
        Err(e) => { panic(f"read: {e}") }
    }
}

// `n` tasks busy for 2 s, frames of 20 ms (as many as the workers: none is
// idle to poll), the first writing a byte after 200 ms to a socket a task
// waits to read: the ms from the write to the reader's wake-up.
async fun busy(n: int) -> int64 {
    let l = listener()
    let a = connected(port_of(l))
    let b = match l.accept() { Ok(s) => s, Err(e) => { panic(f"accept: {e}") } }
    async let r = woken_at(b)
    var hs: [async () -> int64] = []
    for i in 0..n {
        let at = if i == 0 { 10 } else { -1 }
        hs.push(async () => await busy_frames(a, 100, at))
    }
    let wrote = (await task.all(hs))[0]
    return (await r - wrote) / 1000000
}

// A task that only yields until `until` (ms): how many times.
async fun spinner(until: int64) -> int {
    var n = 0
    while time.now_ms() < until {
        for i in 0..100 {
            await task.yield()
        }
        n += 100
    }
    return n
}

// A byte read and written back until the other side closes: how many.
async fun echo_bytes(l: TcpListener) -> int {
    var c = match await l.accept_async() {
        Ok(s) => s
        Err(e) => { return 0 }
    }
    var n = 0
    while true {
        match await c.read_async(1) {
            Ok(b) => {
                if b.len() == 0 {
                    break
                }
                let w = await c.write_async(b)
                n += 1
            }
            Err(e) => { break }
        }
    }
    let gone = c.close()
    return n
}

// The round trips of a byte in 500 ms on a connection, both sides in
// `read_async` and `write_async`, beside `n` tasks that only yield: every
// turn is short and no worker is idle, so only a busy worker's glance at
// the poller wakes either side (MYLA-794).
async fun ping_busy(n: int) -> int {
    let l = listener()
    async let e = echo_bytes(l)
    var c = connected(port_of(l))
    let until = time.now_ms() + 500
    var hs: [async () -> int] = []
    for i in 0..n {
        hs.push(async () => await spinner(until))
    }
    async let spun = task.all(hs)
    var trips = 0
    while time.now_ms() < until {
        let w = await c.write_async([1u8])
        match await c.read_async(1) {
            Ok(b) => { trips += 1 }
            Err(e) => { panic(f"read: {e}") }
        }
    }
    let gone = c.close()
    let s = await spun
    if await e != trips {
        panic("echo")
    }
    return trips
}

#main
async fun main() {
    let a = args()
    let n = match num.parse_int(a[2]) { Some(v) => v as int, None => 0 }
    if a[1] == "busy" {
        print(await busy(n))
    } else if a[1] == "ping-busy" {
        print(await ping_busy(n))
    } else if a[1] == "round-trips" {
        print(await round_trips(n))
    } else if a[1] == "closed" {
        print(await closed())
    } else if a[1] == "accepts" {
        print(await accepts(n, 200))
    } else {
        print(await readers(n))
    }
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class _Built(unittest.TestCase):
    binary = ""
    tmp: tempfile.TemporaryDirectory | None = None

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = write_program(cls.tmp.name, PROGRAM, "reactor.my")
        cls.binary = os.path.join(cls.tmp.name, "reactor")
        native_build(Program(path), cls.binary)

    @classmethod
    def tearDownClass(cls):
        if cls.tmp is not None:
            cls.tmp.cleanup()

    def run_text(self, mode: str, n: int, workers: int = 2) -> str:
        argv, exe = run_argv(self.binary, self.binary, [mode, str(n)])
        env = dict(os.environ, MYLA_THREADS=str(workers))
        p = subprocess.run(argv, executable=exe, capture_output=True, text=True, timeout=300, env=env)
        self.assertEqual((p.stderr, p.returncode), ("", 0))
        return p.stdout


class RoundTrips(_Built):
    def test_round_trips_beside_many_waiting_frames(self):
        # alone and then crowded in one process, the best of five tries
        # each: the machine may be shared
        alone, crowded = (int(w) for w in self.run_text("round-trips", 50000, workers=1).split())
        # µs for 1,000: about the same (colder caches), not several times
        # as much
        self.assertLess(crowded, 1.5 * alone + 5000, f"{crowded} µs beside 50,000 waiting frames, {alone} µs alone")


class Accepts(_Built):
    def cpu(self, waiting: int) -> float:
        """The CPU seconds of 200 connections taken beside `waiting` tasks
        accepting, each by exactly one."""
        argv, exe = run_argv(self.binary, self.binary, ["accepts", str(waiting)])
        env = dict(os.environ, MYLA_THREADS="2")
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            p = subprocess.Popen(argv, executable=exe, stdout=out, stderr=err, env=env)
            _, status, usage = os.wait4(p.pid, 0)
            p.returncode = os.waitstatus_to_exitcode(status)
            out.seek(0)
            err.seek(0)
            self.assertEqual((err.read().decode(), p.returncode, out.read().decode().strip()), ("", 0, "200"))
        return usage.ru_utime + usage.ru_stime

    def test_a_connection_wakes_one_accepting_task(self):
        few = min(self.cpu(200) for _ in range(3))
        many = min(self.cpu(2000) for _ in range(3))
        # CPU seconds: about the same, where each connection woke every task
        # waiting and all but one watched the listener again
        self.assertLess(many, 1.5 * few + 0.05, f"{many:.3f} s beside 2,000 accepting, {few:.3f} s beside 200")


class Closed(_Built):
    def test_a_wait_on_a_socket_closed_ends(self):
        # it waited for good natively, and the next socket with its
        # descriptor started with the closed one's watch (EBADF, as
        # interpreted)
        self.assertEqual(self.run_text("closed", 0), "error error 9 (Other(9)), read 3\n")


class BusyWorkers(_Built):
    def test_a_ready_socket_waits_a_turn_with_every_worker_busy(self):
        # every worker busy with frames of 20 ms: a busy worker glances at
        # the poller once a millisecond has passed (MYLA-755), where it did
        # every 64 frames, 1.28 s of these
        for workers in [1, 2]:
            with self.subTest(workers=workers):
                waited = int(self.run_text("busy", workers, workers=workers))
                self.assertLess(waited, 200, f"a ready socket waited {waited} ms on {workers} busy workers")

    def test_round_trips_beside_tasks_that_only_yield(self):
        # every worker busy with short turns (tasks that only yield): a busy
        # worker glances every 64 turns as well as once a millisecond has
        # passed (MYLA-794). With the millisecond alone a round trip took
        # two of them: 499 a second on 1 worker, where 64 turns gave 98,942
        for workers in [1, 2]:
            with self.subTest(workers=workers):
                trips = int(self.run_text("ping-busy", workers, workers=workers))
                # in 500 ms: 2,500 is 5,000 a second, ten times the cliff
                self.assertGreater(trips, 2500, f"{trips} round trips in 500 ms beside {workers} yielding tasks")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Lots(unittest.TestCase):
    def test_parked_sockets_on_both_runners(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, LOTS, "lots.my")
            binary = os.path.join(tmp, "lots")
            native_build(Program(path), binary)
            argv, exe = run_argv(binary, binary)
            p = subprocess.run(argv, executable=exe, capture_output=True, text=True, timeout=60)
            self.assertEqual((p.stdout, p.returncode), (LOTS_OUT, 0), p.stderr)
            out, err, code = selfhost_run(path)
            self.assertEqual((out, code), (LOTS_OUT, 0), err)


class Readers(_Built):
    def test_tasks_reading_one_pipe_are_woken_in_turn(self):
        r, w = os.pipe()
        data = b"x" * 100000
        try:
            proc_argv, exe = run_argv(self.binary, self.binary, ["readers", "500"])
            env = dict(os.environ, MYLA_THREADS="2")
            p = subprocess.Popen(proc_argv, executable=exe, stdin=r, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=env)
            os.close(r)
            r = -1
            # the readers wait first, then the input comes in pieces and ends
            import time
            time.sleep(0.3)
            for k in range(0, len(data), 10000):
                os.write(w, data[k:k + 10000])
                time.sleep(0.01)
            os.close(w)
            w = -1
            out, err = p.communicate(timeout=120)
        finally:
            for fd in (r, w):
                if fd >= 0:
                    os.close(fd)
        self.assertEqual((err.decode(), p.returncode, out.decode().strip()), ("", 0, str(len(data))))


del _Built

if __name__ == "__main__":
    unittest.main()
