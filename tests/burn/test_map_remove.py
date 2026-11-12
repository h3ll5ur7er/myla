"""Burn test: removing a map's keys takes constant time, and keeps the order
(MYLA-310, D105).

`m.remove(k)` used to rebuild the native table and copy the interpreter's
lists, so emptying a map took time quadratic in its size. Now a removal
leaves a tombstone and a gap in the insertion ranks, natively, and a hole
beside an index of the keys in the interpreter; the table is compacted as it
fills. These tests hold both runners to Python's dict, which keeps insertion
order as D105 does, through thousands of mixed inserts, replacements,
removals and reinsertions (so through every compaction and growth), and time
removal at two sizes: four times the keys must take about four times as long,
not sixteen. (A literal that gives a key twice is in the order test too: the
interpreter used to keep both.) And a map emptied by removals shrinks
(MYLA-429): walking and draining it costs the keys it has left, not the
capacity it once needed."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import (CAN_BUILD_NATIVE, SKIP_REASON, Program, native_build, run_argv,
                                run_source_both_now, selfhost_run, write_program)

_ORDER = """fun next(s: int64) -> int64 {
    return (s * 1103515245 + 12345) % 2147483648
}

// The keys and values in the order `for` visits them, folded by position.
fun digest(m: [int: int]) -> int64 {
    var h: int64 = 0
    var place: int64 = 1
    for k in m {
        h += place * ((k as int64) * 31 + (m[k] as int64))
        place += 1
    }
    return h
}

// The same through `keys()`.
fun digest_keys(m: [int: int]) -> int64 {
    var h: int64 = 0
    var place: int64 = 1
    for k in m.keys() {
        h += place * ((k as int64) * 31 + (m[k] as int64))
        place += 1
    }
    return h
}

fun show(m: [int: int]) -> str {
    var sb = StringBuilder()
    for k in m {
        sb.append(f"{k}={m[k]} ")
    }
    return sb.build()
}

fun show_str(m: [str: int]) -> str {
    var sb = StringBuilder()
    for k in m {
        sb.append(f"{k}={m[k]} ")
    }
    return sb.build()
}

fun main() {
    // mixed inserts, replacements, removals and reinsertions over 700 keys
    var m: [int: int] = [:]
    var copies: [[int: int]] = []
    var s: int64 = 1
    for step in 0..30000 {
        s = next(s)
        let k = ((s >> 8) % 700) as int
        let op = (s >> 4) % 10
        if op < 4 {
            m[k] = step
        } else if op < 8 {
            m.remove(k)
        } else if op == 8 {
            m.remove(k)
            m[k] = -step
        } else if m.contains(k) {
            m[k] = m[k] + 1
        }
        if step % 5000 == 4999 {
            print(f"{m.len()} {digest(m)} {digest_keys(m)}")
            copies.push(m)
        }
    }
    // a copy keeps its order and goes its own way
    var c = copies[1]
    var odd = true
    for k in copies[1] {
        if odd { c.remove(k) }
        odd = !odd
    }
    c[-1] = 1
    print(f"{copies[1].len()} {digest(copies[1])} {c.len()} {digest(c)}")
    // emptied, then filled again: the order is the new insertion order
    for k in m.keys() {
        m.remove(k)
    }
    print(f"{m.len()} {m.contains(3)} [{show(m)}]")
    for i in 0..12 {
        m[(i * 7) % 12] = i
    }
    print(show(m))
    // gaps carried through growth: every other key removed, then many more
    var g: [int: int] = [:]
    for i in 0..100 {
        g[i] = i
    }
    for i in 0..50 {
        g.remove(2 * i)
    }
    for i in 100..400 {
        g[i] = i
    }
    g[1] = -1
    g.remove(3)
    g[3] = -3
    print(f"{g.len()} {digest(g)}")
    // a key given twice in a literal: its first place, its last value
    let dup: [int: str] = [1: "a", 2: "b", 1: "c"]
    print(f"{dup.len()} {dup[1]} {dup.keys()[0]}")
    // string keys, removed and inserted again
    var w: [str: int] = [:]
    for i in 0..300 {
        w[f"k{(i * 37) % 300}"] = i
    }
    for i in 0..300 {
        if i % 3 != 0 { w.remove(f"k{i}") }
    }
    w.remove("k0")
    w["k0"] = 1000
    w["k299"] = 299
    w["k3"] = -3
    print(w.len())
    print(show_str(w))
}
"""


def _wrap(x: int) -> int:
    x %= 2 ** 64
    return x - 2 ** 64 if x >= 2 ** 63 else x


def _digest(m: dict) -> int:
    return _wrap(sum(p * (k * 31 + v) for p, (k, v) in enumerate(m.items(), 1)))


def _show(m: dict) -> str:
    return "".join(f"{k}={v} " for k, v in m.items())


def _expected_order() -> str:
    out = []
    m: dict[int, int] = {}
    copies = []
    s = 1
    for step in range(30000):
        s = (s * 1103515245 + 12345) % 2147483648
        k = (s >> 8) % 700
        op = (s >> 4) % 10
        if op < 4:
            m[k] = step
        elif op < 8:
            m.pop(k, None)
        elif op == 8:
            m.pop(k, None)
            m[k] = -step
        elif k in m:
            m[k] += 1
        if step % 5000 == 4999:
            out.append(f"{len(m)} {_digest(m)} {_digest(m)}")
            copies.append(dict(m))
    c = dict(copies[1])
    for i, k in enumerate(copies[1]):
        if i % 2 == 0:
            del c[k]
    c[-1] = 1
    out.append(f"{len(copies[1])} {_digest(copies[1])} {len(c)} {_digest(c)}")
    m.clear()
    out.append("0 false []")
    for i in range(12):
        m[(i * 7) % 12] = i
    out.append(_show(m))
    g = {i: i for i in range(100)}
    for i in range(50):
        del g[2 * i]
    for i in range(100, 400):
        g[i] = i
    g[1] = -1
    del g[3]
    g[3] = -3
    out.append(f"{len(g)} {_digest(g)}")
    dup = {1: "a", 2: "b", 1: "c"}  # noqa: F601 (the repeated key is the point)
    out.append(f"{len(dup)} {dup[1]} {list(dup)[0]}")
    w: dict[str, int] = {}
    for i in range(300):
        w[f"k{(i * 37) % 300}"] = i
    for i in range(300):
        if i % 3 != 0:
            del w[f"k{i}"]
    del w["k0"]
    w["k0"] = 1000
    w["k299"] = 299
    w["k3"] = -3
    out += [str(len(w)), _show(w)]
    return "\n".join(out) + "\n"


# Removal timed inside the program: n keys inserted, then all removed in a
# scrambled order; it prints the microseconds the removals took. (7919 and
# 104729 are primes that divide none of the sizes the tests use, so both
# orders visit every key.)
_DRAIN = """from std.process import args
from std.num import parse_int
from std.time import now_ns

fun main() {
    let n = match parse_int(args()[1]) {
        Some(v) => v,
        None => 0,
    }
    var m: [int64: int64] = [:]
    var i: int64 = 0
    while i < n {
        m[i * 7919 % n] = i
        i += 1
    }
    let start = now_ns()
    i = 0
    while i < n {
        m.remove(i * 104729 % n)
        i += 1
    }
    let took = now_ns() - start
    if m.len() != 0 {
        panic("keys left")
    }
    print(took / 1000)
}
"""


# A map that once held many keys, walked and drained oldest-first, timed
# inside the program against one that never held more than it keeps
# (MYLA-429, M26): it prints the microseconds of each. Removals never shrank a
# native map, so walking one emptied by them cost the capacity it once
# needed: 20,000 keys taken oldest-first from a map that had held a million
# took 94 s, where a map of 20,000 takes 3 s.
_SHRINK = """from std.process import args
from std.num import parse_int
from std.time import now_ns

fun arg(i: int) -> int64 {
    return match parse_int(args()[i]) {
        Some(v) => v,
        None => 0,
    }
}

// A map grown to `size` keys and left with its newest `keep`: the
// microseconds `rounds` walks over it take, then taking its keys
// oldest-first until it is empty.
fun walk_and_drain(size: int64, keep: int64, rounds: int64) -> int64 {
    var m: [int64: int64] = [:]
    var i: int64 = 0
    while i < size {
        m[i] = i
        i += 1
    }
    i = 0
    while i < size - keep {
        m.remove(i)
        i += 1
    }
    let start = now_ns()
    var sum: int64 = 0
    var r: int64 = 0
    while r < rounds {
        for k in m {
            sum += k - (size - keep)
        }
        r += 1
    }
    var next = size - keep
    while m.len() > 0 {
        var first: int64 = -1
        for k in m {
            first = k
            break
        }
        if first != next {
            panic(f"took {first}, not {next}")
        }
        m.remove(first)
        next += 1
    }
    let took = now_ns() - start
    if sum != rounds * keep * (keep - 1) / 2 {
        panic("the walks went wrong")
    }
    return took / 1000
}

fun main() {
    let size = arg(1)
    let keep = arg(2)
    let rounds = arg(3)
    print(f"{walk_and_drain(size, keep, rounds)} {walk_and_drain(keep, keep, rounds)}")
}
"""

# A queue drained oldest-first by a `for` that leaves at its first key
# (MYLA-496): it prints the microseconds. The loop made the list of all the
# keys before its first step, so the drain was quadratic: 20,000 keys took
# 2.6 s natively and 9.7 s interpreted.
_QUEUE = """from std.process import args
from std.num import parse_int
from std.time import now_ns

fun main() {
    let n: int64 = match parse_int(args()[1]) {
        Some(v) => v,
        None => 0,
    }
    var m: [int64: str] = [:]
    var i: int64 = 0
    while i < n {
        m[i] = f"v{i}"
        i += 1
    }
    let start = now_ns()
    var next: int64 = 0
    while m.len() > 0 {
        var first: int64 = -1
        for k in m {
            first = k
            break
        }
        if first != next {
            panic(f"took {first}, not {next}")
        }
        m.remove(first)
        next += 1
    }
    print((now_ns() - start) / 1000)
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class MapRemove(unittest.TestCase):
    def test_order_after_removes_and_reinserts(self):
        self.assertEqual(run_source_both_now(_ORDER), (_expected_order(), "", 0))

    def _assert_linear(self, micros, small: int, label: str, slack_us: int):
        """Four times the keys within eight times the time (quadratic is
        sixteen), plus `slack_us` for a busy machine; the best of three."""
        a = min(micros(small) for _ in range(3))
        b = min(micros(4 * small) for _ in range(3))
        self.assertLess(b, 8 * a + slack_us, f"{label}: removing {small} keys took {a} us, {4 * small} took {b} us")

    def test_removal_scales_linearly_natively(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, _DRAIN)
            binary = os.path.join(tmp, "drain")
            native_build(Program(path), binary)

            def micros(n: int) -> int:
                argv, exe = run_argv(binary, "drain", [str(n)])
                proc = subprocess.run(argv, executable=exe, capture_output=True, text=True, timeout=300)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                return int(proc.stdout)

            self._assert_linear(micros, 5003, "natively", 20_000)

    def test_removal_scales_linearly_in_the_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, _DRAIN)

            def micros(n: int) -> int:
                out, err, code = selfhost_run(path, [str(n)])
                self.assertEqual(code, 0, err)
                return int(out)

            self._assert_linear(micros, 1999, "interpreted", 100_000)

    def test_a_loop_that_leaves_at_the_first_key_costs_what_it_walked_natively(self):
        # MYLA-496: 20,000 keys took 2.6 s, now milliseconds
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, _QUEUE)
            binary = os.path.join(tmp, "queue")
            native_build(Program(path), binary)

            def micros(n: int) -> int:
                argv, exe = run_argv(binary, "queue", [str(n)])
                proc = subprocess.run(argv, executable=exe, capture_output=True, text=True, timeout=300)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                return int(proc.stdout)

            self._assert_linear(micros, 5000, "natively", 20_000)

    def test_a_loop_that_leaves_at_the_first_key_costs_what_it_walked_in_the_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, _QUEUE)

            def micros(n: int) -> int:
                out, err, code = selfhost_run(path, [str(n)])
                self.assertEqual(code, 0, err)
                return int(out)

            self._assert_linear(micros, 2000, "interpreted", 100_000)

    def _assert_live_size(self, micros, size: int, keep: int, rounds: int, label: str, slack_us: int):
        """The map that held `size` keys within three times the time of the
        one that held `keep` (it was hundreds of times), plus `slack_us`;
        the best of three."""
        runs = [micros(size, keep, rounds) for _ in range(3)]
        once_big = min(r[0] for r in runs)
        always_small = min(r[1] for r in runs)
        self.assertLess(once_big, 3 * always_small + slack_us,
                        f"{label}: {keep} keys left of {size} took {once_big} us, {keep} keys of {keep} {always_small} us")

    def test_a_map_emptied_by_removes_walks_in_its_live_size_natively(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, _SHRINK)
            binary = os.path.join(tmp, "shrink")
            native_build(Program(path), binary)

            def micros(size: int, keep: int, rounds: int) -> tuple[int, int]:
                argv, exe = run_argv(binary, "shrink", [str(size), str(keep), str(rounds)])
                proc = subprocess.run(argv, executable=exe, capture_output=True, text=True, timeout=300)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                a, b = proc.stdout.split()
                return int(a), int(b)

            self._assert_live_size(micros, 200_000, 1000, 100, "natively", 20_000)

    def test_a_map_emptied_by_removes_walks_in_its_live_size_in_the_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, _SHRINK)

            def micros(size: int, keep: int, rounds: int) -> tuple[int, int]:
                out, err, code = selfhost_run(path, [str(size), str(keep), str(rounds)])
                self.assertEqual(code, 0, err)
                a, b = out.split()
                return int(a), int(b)

            self._assert_live_size(micros, 20_000, 200, 20, "interpreted", 100_000)


if __name__ == "__main__":
    unittest.main()
