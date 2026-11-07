"""Burn test: the platform primitives of MYLA-336, called directly (the
user-facing API over them is MYLA-337, MYLA-339 and MYLA-340's).

- entropy: `__random_bytes(n)`;
- file descriptors: `__open(path, flags, mode)`, `__read`, `__write`,
  `__seek(fd, offset, whence)`, `__fstat(fd)`, `__close`;
- children with pipes: `__spawn_piped(program, argv, opts)`, `__read` and
  `__write` on its three descriptors, `__reap`, `__try_reap(pid)`, `__kill`.

Each program runs in the self-hosted interpreter and natively, which must
agree; `scripts/test-target.py` runs the suite for aarch64 (qemu) and wasm32
(Node), where WASI has no processes and the pipes' programs are excused
(`_targets.py`): `PipesOnWasm` checks that each of their primitives is
`Unsupported` (ENOSYS) there instead. A program's call of one is the
primitive warning (D100, D161), as the others' is."""
import os
import subprocess
import tempfile
import unittest

from ._native import (
    CAN_BUILD_NATIVE,
    SKIP_REASON,
    TEST_TARGET,
    Program,
    build_and_run_full,
    selfhost_run,
    write_program,
)
from ._tools import STDLIB_ROOT, selfhost_tool

# What a primitive gave and the errno it left, read at once (a print in the
# interpreter is a write of the host's, which sets the errno again).
HELPERS = """#allow(primitive)
fun e(r: int) -> str {
    return f"{r} {__io_errno()}"
}

#allow(primitive)
fun e64(r: int64) -> str {
    return f"{r} {__io_errno()}"
}

#allow(primitive)
fun es(s: str) -> str {
    return f"{s} {__io_errno()}"
}

"""

ENTROPY = HELPERS + """#allow(primitive)
fun main() {
    let a = __random_bytes(32)
    print(e(a.len()))
    let b = __random_bytes(32)
    var same = 0
    var i = 0
    while i < 32 {
        if a[i] == b[i] {
            same += 1
        }
        i += 1
    }
    print(same < 32)
    print(e(__random_bytes(0).len()))
    // more than one getrandom call gives at once (from 256 bytes a signal
    // may cut one short, from 32 MB the kernel does)
    let big = __random_bytes(100000)
    print(e(big.len()))
    var counts: [int] = []
    i = 0
    while i < 256 {
        counts.push(0)
        i += 1
    }
    for x in big {
        counts[x as int] += 1
    }
    var seen = 0
    for c in counts {
        if c > 0 {
            seen += 1
        }
    }
    print(seen)
    print(e(__random_bytes(-1).len()))
}
"""
ENTROPY_OUT = "32 0\ntrue\n0 0\n100000 0\n256\n0 22\n"

# the open flags: 1 read, 2 write, 4 create, 8 truncate, 16 append, 32 exclusive
FILES = HELPERS + """from std.process import args

#allow(primitive)
fun write(fd: int, s: str) -> str {
    __write(fd, s)
    return f"{__io_errno()}"
}

#allow(primitive)
fun main() {
    let path = args()[1] + "/f.txt"
    let w = __open(path, 2 | 4 | 8, 420)
    print(w >= 0)
    print(write(w, "hello world"))
    print(e64(__seek(w, 0, 1)))
    print(__fstat(w)[0])
    __close(w)

    let r = __open(path, 1, 0)
    print(es(__read(r, 5)))
    print(e64(__seek(r, 0, 1)))
    print(e64(__seek(r, -5, 2)))
    print(es(__read(r, 100)))
    print(e(__read(r, 100).len()))
    print(e64(__seek(r, 1, 0)))
    print(__read(r, 4))
    let st = __fstat(r)
    print(e(st.len()))
    print(st[0])
    print(st[1] & 61440)
    print(st[2] > 1600000000000000000)
    // the descriptor reads, it doesn't write: EBADF
    print(write(r, "x"))
    __close(r)

    // appended wherever the cursor is
    let a = __open(path, 2 | 16, 0)
    print(e64(__seek(a, 0, 0)))
    print(write(a, "!"))
    __close(a)
    let rw = __open(path, 1 | 2, 0)
    print(e64(__seek(rw, 6, 0)))
    print(write(rw, "WORLD"))
    print(e64(__seek(rw, 0, 0)))
    print(__read(rw, 100))
    __close(rw)
    // created (it is there) without truncating: written from the start
    let c = __open(path, 2 | 4, 420)
    print(write(c, "J"))
    __close(c)
    let again = __open(path, 1, 0)
    print(__read(again, 100))
    __close(again)

    // exclusive: EEXIST, then a new file
    print(e(__open(path, 2 | 4 | 32, 420)))
    let fresh = __open(args()[1] + "/new.txt", 2 | 4 | 32, 420)
    print(fresh >= 0)
    print(__fstat(fresh)[0])
    __close(fresh)
    // ENOENT, EISDIR, a NUL in the path and no access asked for (EINVAL)
    print(e(__open(args()[1] + "/missing", 1, 0)))
    print(e(__open(args()[1], 2, 0)))
    print(e(__open(args()[1] + "/a\\0b", 1, 0)))
    print(e(__open(path, 0, 0)))
    print(e(__open(path, 1 | 64, 0)))
    // before the start, another whence: EINVAL
    let d = __open(path, 1, 0)
    print(e64(__seek(d, -1, 0)))
    print(e64(__seek(d, 0, 7)))
    // closed: EBADF
    __close(d)
    print(e64(__seek(d, 0, 0)))
    print(e(__fstat(d).len()))
    print(e(__read(d, 10).len()))
    // the standard output is a pipe here: ESPIPE
    print(e64(__seek(1, 0, 1)))
}
"""
FILES_OUT = """true
0
11 0
11
hello 0
5 0
6 0
world 0
0 0
1 0
ello
3 0
11
32768
true
9
0 0
0
6 0
0
0 0
hello WORLD!
0
Jello WORLD!
-1 17
true
0
-1 2
-1 21
-1 22
-1 22
-1 22
-1 22
-1 22
-1 9
0 9
0 9
-1 29
"""

MODE = """from std.process import args

#allow(primitive)
fun main() {
    let fd = __open(args()[1] + "/private", 2 | 4, 384)
    print(__fstat(fd)[1] & 4095)
    __close(fd)
    let st = __fstat(0)
    print(st.len())
}
"""

PIPES = HELPERS + """fun show(h: [int]) -> str {
    var sb = StringBuilder()
    for x in h {
        if sb.len() > 0 {
            sb.append(" ")
        }
        sb.append(f"{x}")
    }
    return sb.build()
}

#allow(primitive)
fun drain(fd: int) -> str {
    var sb = StringBuilder()
    while true {
        let chunk = __read(fd, 7)
        if chunk.len() == 0 {
            break
        }
        sb.append(chunk)
    }
    return sb.build()
}

#allow(primitive)
fun close_all(h: [int]) {
    __close(h[2])
    __close(h[3])
    __close(h[4])
    __close(h[5])
}

#allow(primitive)
fun main() {
    let none: [str] = []
    // stdin in, stdout out, through cat (found on PATH)
    let h = __spawn_piped("cat", ["cat"], none)
    print(h.len())
    print(h[0])
    print(h[1] > 0)
    __write(h[2], "through cat\\n")
    __write(h[2], "and again\\n")
    __close(h[2])
    print(drain(h[3]))
    print(drain(h[4]).len())
    print(__reap(h[1]))
    close_all(h)

    // stderr and an exit status
    let s = __spawn_piped("/bin/sh", ["sh", "-c", "read x; echo got $x; echo oops >&2; exit 7"], none)
    __write(s[2], "it\\n")
    print(drain(s[3]))
    print(drain(s[4]))
    var st = __try_reap(s[1])
    var waits = 0
    while st == 256 && waits < 5000 {
        __sleep_ns(1000000)
        st = __try_reap(s[1])
        waits += 1
    }
    print(e(st))
    close_all(s)

    // still running, then killed
    let k = __spawn_piped("/bin/sh", ["sh", "-c", "read x"], none)
    print(e(__try_reap(k[1])))
    __kill(k[1], 15)
    print(e(0))
    print(__reap(k[1]))
    close_all(k)
    // the child is gone: no such child (ECHILD), no such process (ESRCH)
    print(e(__try_reap(k[1])))
    __kill(k[1], 15)
    print(e(0))

    // a directory and an environment, as `__spawn_with` takes them
    let env = __spawn_piped("/bin/sh", ["sh", "-c", "pwd; echo $GREETING"], ["/", "", "", "clear", "GREETING=hi"])
    print(drain(env[3]))
    print(__reap(env[1]))
    close_all(env)

    // a write to a child that has ended: EPIPE, and the program goes on
    let t = __spawn_piped("/bin/true", ["true"], none)
    print(__reap(t[1]))
    __write(t[2], "anyone?")
    print(e(0))
    close_all(t)

    // a program that isn't there
    let m = __spawn_piped("/no/such/program", ["x"], none)
    print(show(m))
}
"""
PIPES_OUT = """6
0
true
through cat
and again

0
0
got it

oops

7 0
256 0
0 0
-15
256 10
0 3
/
hi

0
0
0 32
2 0 -1 -1 -1 -1
"""

PIPES_WASM = HELPERS + """fun show(h: [int]) -> str {
    var sb = StringBuilder()
    for x in h {
        if sb.len() > 0 {
            sb.append(" ")
        }
        sb.append(f"{x}")
    }
    return sb.build()
}

#allow(primitive)
fun main() {
    let none: [str] = []
    print(show(__spawn_piped("/bin/cat", ["cat"], none)))
    print(e(__try_reap(1)))
    __kill(1, 15)
    print(e(0))
}
"""


def run_both(source: str, args=()) -> tuple[str, str, int]:
    """`source` in the self-hosted interpreter and built for the test's
    target, which must agree; their (stdout, stderr, exit)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = write_program(tmp, source)
        interp = selfhost_run(path, list(args))
        native = build_and_run_full(Program(path), args=list(args), argv0=path)
    assert interp == native, f"interpreter {interp!r} != native {native!r}"
    return interp


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Entropy(unittest.TestCase):
    def test_random_bytes(self):
        self.assertEqual(run_both(ENTROPY), (ENTROPY_OUT, "", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Descriptors(unittest.TestCase):
    def test_open_read_write_seek_fstat_close(self):
        # each run in a directory of its own, the interpreter's and the build's
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            with tempfile.TemporaryDirectory() as tmp:
                path = write_program(tmp, FILES)
                interp = selfhost_run(path, [a])
                native = build_and_run_full(Program(path), args=[b], argv0=path)
            self.assertEqual(interp, (FILES_OUT, "", 0))
            self.assertEqual(native, interp)

    def test_the_mode_given(self):
        # 0600 under the usual umask; the standard input is a pipe here
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            with tempfile.TemporaryDirectory() as tmp:
                path = write_program(tmp, MODE)
                old = os.umask(0o022)
                try:
                    interp = selfhost_run(path, [a])
                    native = build_and_run_full(Program(path), args=[b], argv0=path)
                finally:
                    os.umask(old)
            self.assertEqual(interp, ("384\n3\n", "", 0))
            self.assertEqual(native, interp)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Pipes(unittest.TestCase):
    def test_spawn_piped_reap_try_reap_kill(self):
        self.assertEqual(run_both(PIPES), (PIPES_OUT, "", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(TEST_TARGET == "wasm32-wasi", "the wasm32 suite's (scripts/test-target.py wasm32-wasi)")
class PipesOnWasm(unittest.TestCase):
    def test_no_processes_is_enosys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, PIPES_WASM)
            out = build_and_run_full(Program(path), argv0=path)
        self.assertEqual(out, ("38 0 -1 -1 -1 -1\n256 38\n0 38\n", "", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Warnings(unittest.TestCase):
    """Outside `std` each is the primitive warning (D100), which `#allow`
    silences (D161), as every I/O primitive's is."""

    CALLS = {
        "__random_bytes": "print(__random_bytes(4).len())",
        "__open": "print(__open(\"/\", 1, 0))",
        "__seek": "print(__seek(0, 0, 1))",
        "__fstat": "print(__fstat(0).len())",
        "__spawn_piped": "print(__spawn_piped(\"/bin/true\", [\"true\"], none).len())",
        "__try_reap": "print(__try_reap(1))",
    }

    def check(self, source: str) -> tuple[str, int]:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, source)
            p = subprocess.run([selfhost_tool("main"), "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                               text=True)
            return p.stderr, p.returncode

    def test_each_is_a_warning(self):
        for name, call in self.CALLS.items():
            with self.subTest(name):
                src = f"fun main() {{\n    let none: [str] = []\n    {call}\n}}\n"
                err, code = self.check(src)
                self.assertEqual(code, 0, err)
                self.assertIn(f"warning[primitive]: '{name}' is a primitive of the standard library", err)
                self.assertEqual(self.check("#allow(primitive)\n" + src), ("", 0))
                self.assertEqual(self.check(f"#allow(primitive({name}))\n" + src), ("", 0))

    def test_their_arguments_are_checked(self):
        cases = {
            "fun main() {\n    print(__open(1, 1, 0))\n}\n": "__open() takes",
            "fun main() {\n    print(__seek(0, 0))\n}\n": "__seek() takes",
            "fun main() {\n    print(__random_bytes(\"4\").len())\n}\n": "__random_bytes() takes",
            "fun main() {\n    print(__spawn_piped(\"x\", [\"x\"]).len())\n}\n": "__spawn_piped() takes",
        }
        for src, msg in cases.items():
            with self.subTest(msg):
                err, code = self.check(src)
                self.assertEqual(code, 1, err)
                self.assertIn(msg, err)


if __name__ == "__main__":
    unittest.main()
