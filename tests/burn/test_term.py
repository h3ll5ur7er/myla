"""Burn test: `std.term`, `std.signal` and their primitives (MYLA-350).

- the terminal: programs under a pseudo-terminal this test opens (Python's
  `pty`, its size set with TIOCSWINSZ) see their standard streams as one and
  its size; with pipes, none and `None`. Raw mode turns echo and canonical
  input off (read back with tcgetattr from this side), keys arrive one by one
  (an arrow's escape sequence, Ctrl-C as a key, not a signal), and `restore`
  turns both back on;
- signals: SIGINT and SIGTERM sent to a running program reach the task
  awaiting `Signals.next()` while another task runs, one sent before the
  program awaits waits for it, a task asked to stop stops waiting, and once
  the program stops listening a signal ends it again; `interrupted()` in a
  program without tasks; a program that never listens ends on SIGINT as
  before;
- `myla repl` on a terminal edits its lines with `std.term` (moves, deletes,
  history, Ctrl-C, Ctrl-D);
- each primitive directly, its warning outside `std` and its arguments
  checked; on wasm32 nothing is a terminal and raw mode and signals are
  `Unsupported`.

Each program runs in the self-hosted interpreter and built for the test's
target, which must agree; `scripts/test-target.py` runs the suite for aarch64
(qemu-user passes the terminal's ioctls and the signals through) and wasm32
(Node), where the terminal and signal classes are excused (`_targets.py`) and
`TermOnWasm` checks the `Unsupported` instead."""
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest

from ._native import (
    CAN_BUILD_NATIVE,
    SKIP_REASON,
    TEST_TARGET,
    Program,
    build_and_run_full,
    native_build,
    run_argv,
    write_program,
)
from ._tools import STDLIB_ROOT, selfhost_tool

COLS, ROWS = 101, 33

# the processes the tests started, killed after each test (a failed one may
# leave its program waiting)
_RUNNING: list[subprocess.Popen] = []


class Case(unittest.TestCase):
    def tearDown(self):
        while _RUNNING:
            p = _RUNNING.pop()
            if p.poll() is None:
                p.kill()
                p.wait()


class Pty:
    """A command running with a pseudo-terminal as its stdin, stdout and
    stderr, `COLS` by `ROWS`; this side keeps the terminal's end open to read
    its mode."""

    def __init__(self, argv, executable=None, env=None):
        self.master, self.slave = pty.openpty()
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        self.proc = subprocess.Popen(argv, executable=executable, stdin=self.slave, stdout=self.slave,
                                     stderr=self.slave, env=env, start_new_session=True)
        _RUNNING.append(self.proc)
        self.out = b""
        self.seen = 0

    def _read(self, timeout: float) -> bool:
        r, _, _ = select.select([self.master], [], [], timeout)
        if not r:
            return False
        try:
            chunk = os.read(self.master, 65536)
        except OSError:
            return False
        self.out += chunk
        return bool(chunk)

    def expect(self, text: str, timeout: float = 60) -> str:
        """What came up to and including `text` since the last expect, with
        CR LF as LF."""
        want = text.replace("\n", "\r\n").encode()
        deadline = time.time() + timeout
        while want not in self.out[self.seen:]:
            if time.time() > deadline:
                raise AssertionError(f"no {text!r} in {self.out[self.seen:]!r}")
            if not self._read(0.1) and self.proc.poll() is not None and not self._read(0.1):
                raise AssertionError(f"ended ({self.proc.returncode}) without {text!r}: {self.out[self.seen:]!r}")
        end = self.out.index(want, self.seen) + len(want)
        got = self.out[self.seen:end]
        self.seen = end
        return got.decode("utf-8", "replace").replace("\r\n", "\n")

    def send(self, data: bytes):
        os.write(self.master, data)

    def lflag(self) -> int:
        return termios.tcgetattr(self.slave)[3]

    def finish(self, timeout: float = 60) -> tuple[str, int]:
        """The rest of the output and the exit status; the terminal closed."""
        out = self.finish_keeping(timeout)
        self.close()
        return out

    def close(self):
        os.close(self.master)
        os.close(self.slave)

    def finish_keeping(self, timeout: float = 60) -> tuple[str, int]:
        """The rest of the output and the exit status; the terminal kept."""
        deadline = time.time() + timeout
        while self.proc.poll() is None and time.time() < deadline:
            self._read(0.1)
        while self._read(0.1):
            pass
        if self.proc.poll() is None:
            self.proc.kill()
        code = self.proc.wait()
        rest = self.out[self.seen:].decode("utf-8", "replace").replace("\r\n", "\n")
        return rest, code


class Built:
    """A program's text, interpreted (`myla run`) and built for the test's
    target: the commands that run each."""

    def __init__(self, source: str):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = write_program(self.tmp.name, source)
        self.binary = os.path.join(self.tmp.name, "prog")
        native_build(Program(self.path), self.binary)

    def commands(self):
        """("interpreted", argv, executable) and ("built", …)."""
        argv, exe = run_argv(self.binary, self.path)
        return [("interpreted", [selfhost_tool("main"), "run", self.path, "--stdlib", STDLIB_ROOT], None),
                ("built", argv, exe)]

    def close(self):
        self.tmp.cleanup()


def env_with(**kv):
    env = dict(os.environ)
    env.pop("NO_COLOR", None)
    env.update(kv)
    return env


TTY = """import std.term as term
from std.term import Stream

fun main() {
    print(f"tty {term.is_tty(Stream.Stdin)} {term.is_tty(Stream.Stdout)} {term.is_tty(Stream.Stderr)}")
    match term.size() {
        Some((cols, rows)) => print(f"size {cols} {rows}")
        None => print("no size")
    }
    match term.size_of(Stream.Stdin) {
        Some((cols, rows)) => print(f"stdin {cols} {rows}")
        None => print("stdin no size")
    }
    print(f"ansi {term.enable_ansi(Stream.Stdout)} colors {term.colors(Stream.Stdout)}")
    match term.raw_mode() {
        Ok(raw) => print("raw")
        Err(e) => print(f"raw: {e}")
    }
}
"""

RAW = """import std.term as term
from std.term import Key
from std.io import stdin

fun name(k: Key) -> str {
    return match k {
        Key.Char(c) => f"Char({c})"
        Key.Ctrl(c) => f"Ctrl({c})"
        Key.Alt(c) => f"Alt({c})"
        Key.Up => "Up"
        Key.Left => "Left"
        Key.Enter => "Enter"
        Key.Escape => "Escape"
        Key.Delete => "Delete"
        Key.F(n) => f"F{n}"
        _ => "another key"
    }
}

fun main() {
    let raw = match term.raw_mode() {
        Ok(r) => r
        Err(e) => panic(f"raw_mode: {e}")
    }
    print("raw")
    var keys = term.key_reader()
    var n = 0
    while n < 7 {
        match keys.next() {
            Ok(Some(k)) => print(f"key {name(k)}")
            Ok(None) => print("end")
            Err(e) => print(f"error: {e}")
        }
        n += 1
    }
    match raw.restore() {
        Ok(()) => print("restored")
        Err(e) => print(f"restore: {e}")
    }
    var input = stdin()
    match input.read_line() {
        Ok(Some(line)) => print(f"line {line}")
        _ => print("no line")
    }
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Terminal(Case):
    @classmethod
    def setUpClass(cls):
        cls.tty = Built(TTY)
        cls.raw = Built(RAW)

    @classmethod
    def tearDownClass(cls):
        cls.tty.close()
        cls.raw.close()

    def test_a_terminal_its_size_and_colours(self):
        for how, argv, exe in self.tty.commands():
            with self.subTest(how):
                t = Pty(argv, exe, env=env_with(TERM="xterm"))
                out, code = t.finish()
                self.assertEqual((out, code), (f"tty true true true\nsize {COLS} {ROWS}\nstdin {COLS} {ROWS}\n"
                                               "ansi true colors true\nraw\n", 0))
                # NO_COLOR and a dumb terminal: no colours, escapes still work
                for env in [env_with(TERM="xterm", NO_COLOR="1"), env_with(TERM="dumb")]:
                    out, code = Pty(argv, exe, env=env).finish()
                    self.assertIn("ansi true colors false\n", out)

    def test_no_terminal_with_pipes(self):
        for how, argv, exe in self.tty.commands():
            with self.subTest(how):
                p = subprocess.run(argv, executable=exe, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                   timeout=120)
                self.assertEqual((p.stdout, p.returncode), ("tty false false false\nno size\nstdin no size\n"
                                                            "ansi false colors false\nraw: not a terminal\n", 0))

    def test_raw_mode_and_back(self):
        for how, argv, exe in self.raw.commands():
            with self.subTest(how):
                t = Pty(argv, exe)
                t.expect("raw\n")
                lflag = t.lflag()
                self.assertEqual(lflag & (termios.ECHO | termios.ICANON | termios.ISIG), 0, oct(lflag))
                # an arrow's sequence, Ctrl-C (a key, no signal), a letter,
                # Alt-x, F5, Delete; then a lone Escape after a pause
                t.send(b"\x1b[A\x03q\x1bx\x1b[15~\x1b[3~")
                self.assertEqual(t.expect("key Delete\n"),
                                 "key Up\nkey Ctrl(c)\nkey Char(q)\nkey Alt(x)\nkey F5\nkey Delete\n")
                t.send(b"\x1b")
                t.expect("key Escape\n")
                t.expect("restored\n")
                lflag = t.lflag()
                self.assertEqual(lflag & (termios.ECHO | termios.ICANON | termios.ISIG),
                                 termios.ECHO | termios.ICANON | termios.ISIG, oct(lflag))
                t.send(b"hello\n")
                out, code = t.finish()
                # the terminal echoes the line again, cooked
                self.assertEqual((out, code), ("hello\nline hello\n", 0))


SIGNALS = """import std.signal as signal
import std.task as task
from std.signal import Signal
from std.io import println

async fun ticker() -> int {
    var n = 0
    while !task.cancelled() {
        await task.sleep(5)
        n += 1
    }
    return n
}

#main
async fun main() {
    let s = match signal.listen() {
        Ok(s) => s
        Err(e) => panic(f"listen: {e}")
    }
    async let t = ticker()
    println("ready")
    // the first comes while nobody waits: it waits for `next`
    await task.sleep(300)
    var k = 0
    while k < 2 {
        match await s.next() {
            Ok(sig) => println(f"got {sig}")
            Err(e) => println(f"error: {e}")
        }
        k += 1
    }
    // a wait stopped by a time limit
    let f = async () => await s.next()
    match await task.timeout(50, f) {
        Some(r) => println("a signal?")
        None => println("timed out")
    }
    let pending = match s.try_next() {
        Some(sig) => "a signal"
        None => "none"
    }
    println(f"pending {pending}")
    task.cancel(t)
    println(f"ticked {await t > 0}")
    s.close()
    println("default again")
    await task.sleep(60000)
    println("not here")
}
"""

INTERRUPTED = """import std.signal as signal
import std.task as task
from std.io import println

#main
async fun main() {
    println("ready")
    match await signal.interrupted() {
        Ok(sig) => println(f"got {sig}")
        Err(e) => println(f"error: {e}")
    }
    println("again")
    await task.sleep(60000)
    println("not here")
}
"""

NEVER = """import std.task as task
from std.io import println

#main
async fun main() {
    println("ready")
    await task.sleep(60000)
    println("not here")
}
"""

IGNORED = """import std.signal as signal
import std.task as task
from std.io import println

#main
async fun main() {
    match signal.listen() {
        Ok(s) => s.close()
        Err(e) => panic(f"listen: {e}")
    }
    println("ready")
    await task.sleep(60000)
}
"""


class Lines:
    """A command's stdout read line by line as it runs."""

    def __init__(self, argv, exe, preexec_fn=None):
        self.proc = subprocess.Popen(argv, executable=exe, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, preexec_fn=preexec_fn)
        _RUNNING.append(self.proc)

    def line(self) -> str:
        return self.proc.stdout.readline()

    def signal(self, sig):
        self.proc.send_signal(sig)

    def finish(self, timeout: float = 60) -> tuple[str, str, int]:
        try:
            out, err = self.proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            out, err = self.proc.communicate()
        return out, err, self.proc.returncode


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Signals(Case):
    @classmethod
    def setUpClass(cls):
        cls.signals = Built(SIGNALS)
        cls.interrupted = Built(INTERRUPTED)
        cls.never = Built(NEVER)
        cls.ignored = Built(IGNORED)

    @classmethod
    def tearDownClass(cls):
        for b in [cls.signals, cls.interrupted, cls.never, cls.ignored]:
            b.close()

    def test_awaited_while_another_task_runs(self):
        for how, argv, exe in self.signals.commands():
            with self.subTest(how):
                p = Lines(argv, exe)
                self.assertEqual(p.line(), "ready\n")
                p.signal(signal.SIGINT)
                self.assertEqual(p.line(), "got interrupt\n")
                p.signal(signal.SIGTERM)
                self.assertEqual(p.line(), "got terminate\n")
                self.assertEqual([p.line() for _ in range(4)],
                                 ["timed out\n", "pending none\n", "ticked true\n", "default again\n"])
                time.sleep(0.2)
                p.signal(signal.SIGINT)
                out, err, code = p.finish()
                self.assertEqual((out, err, code), ("", "", -signal.SIGINT))

    def test_interrupted_without_tasks(self):
        for how, argv, exe in self.interrupted.commands():
            for sig, name in [(signal.SIGINT, "interrupt"), (signal.SIGTERM, "terminate")]:
                with self.subTest(how, sig=name):
                    p = Lines(argv, exe)
                    self.assertEqual(p.line(), "ready\n")
                    time.sleep(0.2)
                    p.signal(sig)
                    self.assertEqual([p.line(), p.line()], [f"got {name}\n", "again\n"])
                    time.sleep(0.2)
                    p.signal(signal.SIGTERM)
                    self.assertEqual(p.finish(), ("", "", -signal.SIGTERM))

    def test_a_program_that_never_listens_ends(self):
        for how, argv, exe in self.never.commands():
            for sig in [signal.SIGINT, signal.SIGTERM]:
                with self.subTest(how, sig=sig):
                    p = Lines(argv, exe)
                    self.assertEqual(p.line(), "ready\n")
                    p.signal(sig)
                    self.assertEqual(p.finish(), ("", "", -sig))

    def test_an_ignored_signal_stays_ignored(self):
        # started with SIGINT ignored (`nohup`, a background job): after the
        # last listener, it is ignored again, not given its default
        for how, argv, exe in self.ignored.commands():
            with self.subTest(how):
                p = Lines(argv, exe, preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN))
                self.assertEqual(p.line(), "ready\n")
                p.signal(signal.SIGINT)
                time.sleep(0.3)
                self.assertIsNone(p.proc.poll())
                p.signal(signal.SIGTERM)
                self.assertEqual(p.finish(), ("", "", -signal.SIGTERM))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Repl(Case):
    """`myla repl` on a terminal edits its lines with `std.term`."""

    def test_editing_history_and_control_keys(self):
        t = Pty([selfhost_tool("main"), "repl", "--stdlib", STDLIB_ROOT], env=env_with(TERM="xterm"))
        t.expect("myla> ")
        # raw while it waits for a line
        self.assertEqual(t.lflag() & (termios.ECHO | termios.ICANON), 0)
        # "2 * 3", two lefts, the '*' deleted and a '+' typed: 2 + 3
        t.send(b"2 * 3\x1b[D\x1b[D\x7f+\r")
        t.expect("\n5\n")
        t.expect("myla> ")
        # the line again from the history, then Home and a digit
        t.send(b"\x1b[A\x01" + b"1\r")
        t.expect("\n15\n")
        t.expect("myla> ")
        # an input over two lines continues after the prompt "...   "
        t.send(b"fun f(x: int) -> int {\r")
        t.expect("...   ")
        t.send(b"return x * 7 }\r")
        t.expect("myla> ")
        t.send(b"f(6)\r")
        t.expect("\n42\n")
        t.expect("myla> ")
        # Ctrl-C drops the line, Ctrl-U and Ctrl-K kill, Ctrl-W a word
        t.send(b"oops\x03")
        t.expect("^C\n")
        t.expect("myla> ")
        t.send(b"junk\x15" + b"9 junk\x17\x1b[D\x0b\r")
        t.expect("\n9\n")
        t.expect("myla> ")
        t.send(b"\x04")
        lflag = t.lflag
        out, code = t.finish_keeping()
        self.assertEqual(code, 0, out)
        # the terminal as it was once the session ended
        self.assertEqual(lflag() & (termios.ECHO | termios.ICANON), termios.ECHO | termios.ICANON)
        t.close()

    def test_pipes_read_plain_lines(self):
        p = subprocess.run([selfhost_tool("main"), "repl", "--stdlib", STDLIB_ROOT], input="1 + 1\n",
                           capture_output=True, text=True, timeout=120)
        self.assertEqual((p.stdout, p.returncode), ("2\n", 0))
        self.assertEqual(p.stderr, "myla> myla> \n")


PASTE = """import std.term as term
import std.time as time
from std.term import Key

// 2,000 characters typed (a paste), the line drawn after each as
// `Editor.read_line` does
fun main() {
    var ed = term.line_edit(0)
    let t0 = time.now_ms()
    var drawn = 0
    for i in 0..2000 {
        let s = ed.apply(Key.Char('x'), [])
        drawn += ed.render("> ", 80).len()
    }
    print(f"{drawn} {time.now_ms() - t0}")
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class LongLines(Case):
    """M22: drawing a line costs what is drawn, not the line's length
    squared: 2,000 characters typed one by one took 17 s natively."""

    def test_a_paste_draws_in_linear_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, PASTE)
            out, err, code = build_and_run_full(Program(path), argv0=path)
        self.assertEqual((err, code), ("", 0))
        drawn, ms = map(int, out.split())
        # each draw: "\r> ", the last 77 characters at most, the clear, "\r",
        # the move to the cursor after them
        self.assertEqual(drawn, sum(len(f"\r> {'x' * min(n, 77)}\x1b[K\r\x1b[{2 + min(n, 77)}C")
                                    for n in range(1, 2001)))
        self.assertLess(ms, 2000, out)


WASM = """import std.term as term
from std.term import Stream
import std.signal as signal

fun main() {
    let size = match term.size() {
        Some(cr) => "a size"
        None => "no size"
    }
    print(f"tty {term.is_tty(Stream.Stdin)} {term.is_tty(Stream.Stdout)} {size}")
    print(f"ansi {term.enable_ansi(Stream.Stdout)} colors {term.colors(Stream.Stdout)}")
    match term.raw_mode() {
        Ok(r) => print("raw?")
        Err(e) => print(f"raw: {e}")
    }
    match signal.listen() {
        Ok(s) => print("listening?")
        Err(e) => print(f"listen: {e}")
    }
}
"""
WASM_OUT = """tty false false no size
ansi false colors false
raw: terminals are not supported on this target
listen: signals are not supported on this target
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(TEST_TARGET == "wasm32-wasi", "the wasm32 suite's (scripts/test-target.py wasm32-wasi)")
class TermOnWasm(Case):
    def test_no_terminal_and_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, WASM)
            out = build_and_run_full(Program(path), argv0=path)
        self.assertEqual(out, (WASM_OUT, "", 0))


PRIMITIVES = """#allow(primitive)
fun e(r: int) -> str {
    return f"{r} {__io_errno()}"
}

#allow(primitive)
fun main() {
    print(f"{__term_is_tty(0)} {__term_is_tty(-1)}")
    print(e(__term_size(0)))
    print(e(__term_size(-1)))
    let m = __term_get(0)
    print(f"{m.len()} {__io_errno()}")
    print(e(__term_set(0, "")))
    print(e(__term_raw(0)))
    print(e(__term_raw(-1)))
    print(e(__term_vt(1)))
    print(e(__signal_take(-1)))
    let h = __signal_listen(1)
    print(f"{h >= 0} {__io_errno()}")
    let h2 = __signal_listen(1)
    print(h2 == h)
    print(e(__signal_listen(0)))
    print(e(__signal_listen(0)))
    print(e(__signal_listen(0)))
}
"""
PRIMITIVES_OUT = """0 0
-1 25
-1 9
0 25
-1 22
-1 25
-1 9
-1 25
-1 9
true 0
true
0 0
0 0
0 0
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Primitives(Case):
    """The primitives directly, with no terminal (stdin from /dev/null): what
    a port to another system must give (docs/Language/Standard-library/Term.md)."""

    def test_without_a_terminal(self):
        b = Built(PRIMITIVES)
        try:
            for how, argv, exe in b.commands():
                with self.subTest(how):
                    p = subprocess.run(argv, executable=exe, capture_output=True, text=True,
                                       stdin=subprocess.DEVNULL, timeout=120)
                    self.assertEqual((p.stdout, p.stderr, p.returncode), (PRIMITIVES_OUT, "", 0))
        finally:
            b.close()

    def test_the_mode_on_a_terminal(self):
        src = """#allow(primitive)
fun main() {
    let m = __term_get(0)
    print(f"{m.len() > 0} {__term_raw(0)} {__term_set(0, m)} {__term_set(0, "x")} {__io_errno()}")
}
"""
        b = Built(src)
        try:
            for how, argv, exe in b.commands():
                with self.subTest(how):
                    out, code = Pty(argv, exe).finish()
                    self.assertEqual((out, code), ("true 0 0 -1 22\n", 0))
        finally:
            b.close()


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Warnings(Case):
    """Outside `std` each primitive is the primitive warning (D100), which
    `#allow` silences (D161)."""

    CALLS = {
        "__term_is_tty": "print(__term_is_tty(0))",
        "__term_size": "print(__term_size(0))",
        "__term_get": "print(__term_get(0))",
        "__term_set": "print(__term_set(0, \"\"))",
        "__term_raw": "print(__term_raw(0))",
        "__term_vt": "print(__term_vt(1))",
        "__signal_listen": "print(__signal_listen(0))",
        "__signal_take": "print(__signal_take(-1))",
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
                src = f"fun main() {{\n    {call}\n}}\n"
                err, code = self.check(src)
                self.assertEqual(code, 0, err)
                self.assertIn(f"warning[primitive]: '{name}' is a primitive of the standard library", err)
                self.assertEqual(self.check("#allow(primitive)\n" + src), ("", 0))
                self.assertEqual(self.check(f"#allow(primitive({name}))\n" + src), ("", 0))

    def test_their_arguments_are_checked(self):
        cases = {
            "fun main() {\n    print(__term_size())\n}\n": "__term_size() takes (fd: int)",
            "fun main() {\n    print(__term_set(0, 1))\n}\n": "__term_set() takes (fd: int, mode: str)",
            "fun main() {\n    let s: int = __term_get(0)\n}\n": "",
            "fun main() {\n    print(__signal_take(\"h\"))\n}\n": "__signal_take() takes (h: int)",
        }
        for src, msg in cases.items():
            with self.subTest(msg):
                err, code = self.check(src)
                self.assertEqual(code, 1, err)
                self.assertIn(msg, err)


if __name__ == "__main__":
    unittest.main()
