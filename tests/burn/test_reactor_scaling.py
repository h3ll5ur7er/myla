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
- `Readers`: 500 tasks read one pipe to its end (`read_to_end_async`), each
  woken in turn as the input comes and ends; every byte is read once and
  every task ends (on every target: wasm32's poller too).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, Program, native_build, run_argv, write_program

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

#main
async fun main() {
    let a = args()
    let n = match num.parse_int(a[2]) { Some(v) => v as int, None => 0 }
    if a[1] == "round-trips" {
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
