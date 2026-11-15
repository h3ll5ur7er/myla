"""The Windows target's first step (MYLA-702, D210 to D215): `myla build
--target x86_64-windows` gives a static console `.exe` (PE32+, x86-64,
importing only kernel32.dll, D212), assembled by clang, its import library
made by llvm-dlltool and linked by lld-link (D211), which runs under Wine
(D213): it prints what the program prints, the same bytes as on Linux (UTF-8,
`\\n` as is, D215), ends with its exit code (D216) and reports a runtime error
as on Linux. What isn't there yet says so (D210): random bytes are
`Unsupported`. MYLA-703: tasks run on `MYLA_THREADS` workers,
threads of their own, and a stack overflow is reported as on Linux
(`Workers`); MYLA-717: a frame of a page or more is probed (`StackProbes`,
and `FramesOnWindows` on Windows itself, MYLA-708's runner).

Files, directories and paths (MYLA-704): std.fs over kernel32 in UTF-16,
Windows' errors as Linux's causes where a program sees them, and std.path
on Windows' paths (`std/path_windows.my`, the loader's copy for the target).

Child processes (MYLA-705): `Children` runs std.process with a Windows
program of its own as the child, and a test harness's cases as children.

Skipped where clang, llvm-dlltool, lld-link or Wine is missing (CI installs
them, and MYLA_REQUIRE_TARGETS makes a missing one fail there).
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, wine, wine_env
from ._tools import STDLIB_ROOT, selfhost_tool

TOOLS = ("clang", "llvm-dlltool", "lld-link")
HAVE_WINDOWS = all(shutil.which(t) for t in TOOLS) and bool(wine())
WINDOWS_SKIP = "the Windows tests need clang, llvm-dlltool, lld-link and Wine"


@unittest.skipUnless(os.environ.get("MYLA_REQUIRE_TARGETS"), "MYLA_REQUIRE_TARGETS is not set")
class WindowsTools(unittest.TestCase):
    """CI sets MYLA_REQUIRE_TARGETS: a missing tool fails there instead of
    skipping the target's tests unnoticed (MYLA-268)."""

    def test_the_tools_are_there(self):
        self.assertTrue(HAVE_WINDOWS, WINDOWS_SKIP)


def pe_facts(path: str) -> dict:
    """What a PE file's headers say: its machine, whether it is PE32+, its
    subsystem, and the DLLs its import directory names (lowercase)."""
    with open(path, "rb") as fh:
        data = fh.read()
    assert data[:2] == b"MZ", "not an MZ executable"
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe + 4] == b"PE\0\0", "no PE signature"
    machine, nsections = struct.unpack_from("<HH", data, pe + 4)
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    subsystem = struct.unpack_from("<H", data, opt + 68)[0]
    import_rva = struct.unpack_from("<I", data, opt + 112 + 8)[0]
    sections = []
    for k in range(nsections):
        at = opt + opt_size + 40 * k
        vsize, va, rsize, raw = struct.unpack_from("<IIII", data, at + 8)
        sections.append((va, max(vsize, rsize), raw))

    def offset(rva: int) -> int:
        for va, size, raw in sections:
            if va <= rva < va + size:
                return raw + rva - va
        raise AssertionError(f"RVA {rva:#x} in no section")

    dlls = []
    if import_rva:
        at = offset(import_rva)
        while True:
            name_rva = struct.unpack_from("<I", data, at + 12)[0]
            if name_rva == 0:
                break
            start = offset(name_rva)
            dlls.append(data[start:data.index(b"\0", start)].decode().lower())
            at += 20
    return {"machine": machine, "pe32plus": magic == 0x20B, "subsystem": subsystem, "dlls": dlls}


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WINDOWS, WINDOWS_SKIP)
class HelloWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wine_env()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def build(self, source: str, *flags: str, out: str | None = "prog.exe") -> subprocess.CompletedProcess:
        with open(os.path.join(self.tmp, "main.my"), "w", encoding="utf-8") as fh:
            fh.write(source)
        argv = [selfhost_tool("main"), "build", "main.my", "--target", "x86_64-windows", "--stdlib", STDLIB_ROOT, *flags]
        if out is not None:
            argv += ["-o", out]
        return subprocess.run(argv, capture_output=True, text=True, cwd=self.tmp, timeout=300)

    def run_exe(self, *args: str, exe: str = "prog.exe", stdin: bytes = b"") -> subprocess.CompletedProcess:
        return subprocess.run([*wine(), os.path.join(self.tmp, exe), *args], input=stdin,
                              capture_output=True, cwd=self.tmp, timeout=120)

    def build_and_run(self, source: str, *args: str) -> subprocess.CompletedProcess:
        built = self.build(source)
        self.assertEqual((built.stderr, built.returncode), ("", 0))
        return self.run_exe(*args)

    def test_hello_world_is_a_static_console_exe(self):
        built = self.build('fun main() {\n    print("hello, world")\n}\n', out=None)
        self.assertEqual((built.stdout, built.stderr, built.returncode), ("", "", 0))
        # D217: `a.exe` without `-o`; nothing left beside it
        self.assertEqual(sorted(os.listdir(self.tmp)), ["a.exe", "main.my"])
        facts = pe_facts(os.path.join(self.tmp, "a.exe"))
        self.assertEqual(facts, {"machine": 0x8664, "pe32plus": True, "subsystem": 3, "dlls": ["kernel32.dll"]})
        ran = self.run_exe(exe="a.exe")
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"hello, world\n", b"", 0))

    def test_utf8_and_newlines_as_is(self):
        # D215: the same bytes as on Linux, no CRLF
        ran = self.build_and_run('from std.io import eprintln\nfun main() {\n    print("h\\u{e9}llo, w\\u{f6}rld \\u{2713} \\u{1f600}")\n'
                                 '    eprintln("to stderr")\n    print("a\\r\\nb\\n")\n}\n')
        want = "héllo, wörld ✓ 😀\na\r\nb\n\n".encode()
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (want, b"to stderr\n", 0))

    def test_the_exit_code(self):
        ran = self.build_and_run('from std.process import exit\nfun main() {\n    print("bye")\n    exit(7)\n}\n')
        self.assertEqual((ran.stdout, ran.returncode), (b"bye\n", 7))

    def test_a_runtime_error(self):
        ran = self.build_and_run('fun main() {\n    let xs = [1, 2, 3]\n    var i = 2\n    i += 5\n    print(xs[i])\n}\n')
        self.assertEqual(ran.returncode, 1)
        self.assertEqual(ran.stdout, b"")
        # as on Linux (D183): the values, then where
        self.assertEqual(ran.stderr, b"runtime error: list index 7 out of bounds (len 3)\n  --> main.my:5:13\n")

    def test_arguments_and_the_environment(self):
        # the command line split as Windows' C runtime splits it, in UTF-8
        src = ('from std.process import args, env\n'
               'fun main() {\n'
               '    let a = args()\n'
               '    print(a[0].ends_with("prog.exe"))\n'
               '    var i = 1\n'
               '    while i < a.len() {\n'
               '        print(f"[{a[i]}]")\n'
               '        i += 1\n'
               '    }\n'
               '    print(env("MYLA_WIN_TEST").unwrap_or("none"))\n'
               '    print(env("MYLA_WIN_NONE").unwrap_or("none"))\n'
               '}\n')
        built = self.build(src)
        self.assertEqual((built.stderr, built.returncode), ("", 0))
        os.environ["MYLA_WIN_TEST"] = "v\u00e4lue=1"
        try:
            ran = self.run_exe("plain", "two words", 'quo"te', "back\\slash", "tail\\", "", "\u00e9\u4e2d")
        finally:
            del os.environ["MYLA_WIN_TEST"]
        want = 'true\n[plain]\n[two words]\n[quo"te]\n[back\\slash]\n[tail\\]\n[]\n[\u00e9\u4e2d]\nv\u00e4lue=1\nnone\n'
        self.assertEqual((ran.stdout.decode(), ran.stderr, ran.returncode), (want, b"", 0))

    def test_strings_lists_and_maps(self):
        # the heap (VirtualAlloc's chunks) and a big cell of its own
        src = ('fun main() {\n'
               '    var m: [str: int] = [:]\n'
               '    var xs: [int] = []\n'
               '    var i = 0\n'
               '    while i < 300000 {\n'
               '        xs.push(i)\n'
               '        if i % 1000 == 0 { m[f"k{i}"] = i }\n'
               '        i += 1\n'
               '    }\n'
               '    var sum = 0\n'
               '    for x in xs { sum += x % 7 }\n'
               '    print(f"{xs.len()} {m.len()} {m["k299000"]} {sum}")\n'
               '}\n')
        ran = self.build_and_run(src)
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"300000 300 299000 899997\n", b"", 0))

    def test_reading_the_standard_input(self):
        src = ('from std.io import stdin\n'
               'fun main() {\n'
               '    var r = stdin()\n'
               '    while true {\n'
               '        match r.read_line() {\n'
               '            Ok(Some(l)) => { print(f"<{l}>") },\n'
               '            _ => { break },\n'
               '        }\n'
               '    }\n'
               '}\n')
        built = self.build(src)
        self.assertEqual((built.stderr, built.returncode), ("", 0))
        ran = self.run_exe(stdin="one\ntw\u00f6\n".encode())
        self.assertEqual((ran.stdout.decode(), ran.stderr, ran.returncode), ("<one>\n<tw\u00f6>\n", b"", 0))

    def test_what_isnt_there_yet_says_so(self):
        # D210: random bytes are `Unsupported` until MYLA-722, and with them
        # a temporary directory's name
        src = ('import std.fs as fs\n'
               'fun main() {\n'
               '    match fs.make_temp_dir() {\n'
               '        Ok(d) => { print("made") },\n'
               '        Err(e) => { print(f"{e}") },\n'
               '    }\n'
               '}\n')
        ran = self.build_and_run(src)
        self.assertEqual((ran.stdout, ran.returncode), (b"unsupported (Unsupported)\n", 0))

    def test_files_and_directories(self):
        # MYLA-704: names in UTF-8 made UTF-16, an append at the end, a
        # listing, metadata, renames and removals, and the errors as Linux
        # gives them (D219, D220)
        src = r'''import std.fs as fs
import std.bytes as bytes
from std.io import Write, Seek, SeekFrom
fun unit(r: Result<(), fs.IoError>) -> str {
    return match r {
        Ok(()) => "ok"
        Err(e) => fs.io_error_name(e)
    }
}
fun text(r: Result<str, fs.IoError>) -> str {
    return match r {
        Ok(s) => s
        Err(e) => fs.io_error_name(e)
    }
}
fun main() {
    print(unit(fs.make_dir_all("d\u{e9}/sub")))
    print(unit(fs.write_to_file("d\u{e9}/\u{4e2d}.txt", "h\u{e9}llo")))
    var f = match fs.open_append("d\u{e9}/\u{4e2d}.txt") {
        Ok(f) => f
        Err(e) => panic(f"{e}")
    }
    let s = f.seek(SeekFrom.Start(0))
    let w = f.write(bytes.from_str("!"))
    let c = f.close()
    print(text(fs.read_to_string("d\u{e9}\\\u{4e2d}.txt")))
    print(match fs.list_dir("d\u{e9}") {
        Ok(ns) => ns.join(",")
        Err(e) => fs.io_error_name(e)
    })
    print(match fs.metadata("d\u{e9}/\u{4e2d}.txt") {
        Ok(m) => f"{m.size} {m.is_file()} {m.permissions:o} {m.modified_ns > 0}"
        Err(e) => fs.io_error_name(e)
    })
    print(fs.is_dir("d\u{e9}/sub") && !fs.is_file("d\u{e9}/sub") && !fs.exists("nothing"))
    print(text(fs.read_to_string("d\u{e9}")))
    print(unit(fs.remove_file("d\u{e9}/sub")))
    print(unit(fs.remove_dir("d\u{e9}")))
    print(unit(fs.make_dir("d\u{e9}/\u{4e2d}.txt/x")))
    print(unit(fs.make_dir("d\u{e9}/sub")))
    print(unit(fs.rename("d\u{e9}/\u{4e2d}.txt", "d\u{e9}/b.txt")))
    print(text(fs.read_to_string("d\u{e9}/\u{4e2d}.txt")))
    print(unit(fs.remove_dir_all("d\u{e9}")))
    print(fs.exists("d\u{e9}"))
}
'''
        ran = self.build_and_run(src)
        want = ("ok\nok\nh\u00e9llo!\nsub,\u4e2d.txt\n7 true 666 true\ntrue\nIsADirectory\nIsADirectory\nNotEmpty\n"
                "NotADirectory\nAlreadyExists\nok\nNotFound\nok\nfalse\n")
        self.assertEqual((ran.stdout.decode(), ran.stderr, ran.returncode), (want, b"", 0))
        self.assertEqual(sorted(os.listdir(self.tmp)), ["main.my", "prog.exe"])

    def test_windows_paths(self):
        # D215: std.path is Windows' there (a `\` separates, a drive or a
        # UNC share starts a path) and writes `/`; the working directory is
        # Windows' own path (Wine's drive Z: is the root)
        src = r'''import std.path as path
import std.fs as fs
import std.glob as glob
fun main() {
    print(path.join("a\\", "b"))
    print(path.join("C:\\x", "\\y"))
    print(path.parent("C:\\a\\b").unwrap_or("none"))
    print(path.file_name("\\\\srv\\share").unwrap_or("none"))
    print(path.normalize("C:\\a\\..\\b\\.\\c"))
    print(path.is_absolute("C:/a") && !path.is_absolute("/a") && path.is_absolute("//srv/share"))
    print(path.relative("C:\\a\\b", "c:/a/d").unwrap_or("none"))
    let cwd = match fs.current_dir() {
        Ok(d) => d
        Err(e) => panic(f"{e}")
    }
    print(cwd)
    print(path.is_absolute(cwd) && path.anchor(cwd) == "Z:\\")
    print(fs.is_file(path.join(cwd, "main.my")))
    print(glob.matches("*/*.my", "src\\main.my"))
    match fs.make_dir_all(cwd + "\\deep\\er") {
        Ok(()) => print(fs.is_dir("deep/er"))
        Err(e) => print(f"{e}")
    }
}
'''
        ran = self.build_and_run(src)
        work = "Z:" + os.path.realpath(self.tmp).replace("/", "\\")
        want = f"a\\b\nC:\\y\nC:\\a\nnone\nC:/b/c\ntrue\n../d\n{work}\ntrue\ntrue\ntrue\ntrue\n"
        self.assertEqual((ran.stdout.decode(), ran.stderr, ran.returncode), (want, b"", 0))

    def test_tasks(self):
        # children, an actor, a sleep through the poller's timers, and the
        # clock (on one worker in MYLA-702, D221; on every CPU's since
        # MYLA-703)
        src = ('import std.task as task\n'
               'import std.time as time\n'
               'actor Counter {\n    n: int\n}\n'
               'impl Counter {\n    fun add(var self, k: int) -> int {\n        self.n = self.n + k\n        return self.n\n    }\n}\n'
               'async fun slow(n: int) -> int {\n    await task.sleep(50)\n    return n * 10\n}\n'
               'async fun main() {\n'
               '    let start = time.now()\n'
               '    async let a = slow(1)\n'
               '    async let b = slow(2)\n'
               '    print(await a + await b)\n'
               '    let c = Counter { n: 0 }\n'
               '    for i in 0..10 { let r = await c.add(i) }\n'
               '    print(await c.add(0))\n'
               '    let ms = start.elapsed().as_millis()\n'
               '    print(ms >= 50 && ms < 5000)\n'
               '}\n')
        ran = self.build_and_run(src)
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"30\n45\ntrue\n", b"", 0))

# A child for `Children`: what its first argument says, `args` its other
# arguments one a line in brackets, `cat` its input back, `exit N` the
# status N, `streams` a byte on each stream, `env NAME` a variable (or
# "none"), `big N` N bytes on each stream, `sleep MS`.
HELPER = """import std.task as task
from std.process import args, exit, env
from std.io import write, stdin

fun number(s: str) -> int {
    var n = 0
    var sign = 1
    for c in s {
        if c == '-' { sign = -1 } else { n = n * 10 + (c - '0') }
    }
    return sign * n
}

#main
async fun main() {
    let a = args()
    let mode = a[1]
    if mode == "args" {
        var i = 2
        while i < a.len() {
            print(f"[{a[i]}]")
            i += 1
        }
    } else if mode == "cat" {
        var r = stdin()
        while true {
            match r.read_line() {
                Ok(Some(l)) => { print(l) },
                _ => { break },
            }
        }
    } else if mode == "exit" {
        exit(number(a[2]))
    } else if mode == "streams" {
        let o = write(1, "o")
        let e = write(2, "e")
    } else if mode == "env" {
        print(env(a[2]).unwrap_or("none"))
    } else if mode == "big" {
        var sb = StringBuilder()
        for i in 0..1000 { sb.append("x") }
        let k = sb.build()
        for i in 0..number(a[2]) / 1000 {
            let o = write(1, k)
            let e = write(2, k)
        }
    } else if mode == "sleep" {
        await task.sleep(number(a[2]))
    }
}
"""

# What `Children` runs: std.process on Windows (MYLA-705).
CHILDREN = r"""import std.task as task
from std.process import run, command, run_async, Output, SpawnError, ExitStatus
from std.ioerror import IoError
from std.io import buffered
import std.bytes as bytes

fun said(r: Result<Output, SpawnError>) -> str {
    return match r {
        Ok(o) => f"{bytes.to_str(o.stdout)}|{bytes.to_str(o.stderr)}|{status(Ok(o.status))}"
        Err(e) => f"error {e}"
    }
}

fun status(r: Result<ExitStatus, IoError>) -> str {
    return match r {
        Ok(ExitStatus.Exited(c)) => f"exit {c}"
        Ok(ExitStatus.Signaled(s)) => f"signal {s}"
        Err(e) => f"error {e}"
    }
}

fun polled(r: Result<Option<ExitStatus>, IoError>) -> str {
    return match r {
        Ok(Some(s)) => status(Ok(s))
        Ok(None) => "running"
        Err(e) => f"error {e}"
    }
}

fun done(r: Result<(), IoError>) -> str {
    return match r {
        Ok(()) => "ok"
        Err(e) => f"error {e}"
    }
}

fun line(r: Result<Option<str>, IoError>) -> str {
    return match r {
        Ok(Some(l)) => l
        Ok(None) => "<end>"
        Err(e) => f"error {e}"
    }
}

fun main_sync() {
    let h = "./helper.exe"
    print(said(run(h, ["args", "plain", "two words", "quo\"te", "back\\slash", "tail\\", "", "\u{e9}\u{4e2d}", "a\\\\\"b", "\tx"])))
    print(said(run("helper", ["args", "found on PATH"])))
    print(said(run("HELPER.EXE", ["args", "with its extension"])))
    print(said(run(h, ["exit", "70000"])))
    print(said(run(h, ["exit", "-2"])))
    print(said(run(h, ["streams"])))
    print(said(command(h).arg("cat").stdin("fed\nto it\n").output()))
    print(said(command(h).args(["env", "MYLA_A"]).env("MYLA_A", "set").output()))
    print(said(command(h).args(["env", "MYLA_B"]).env_remove("MYLA_B").output()))
    print(said(command(h).args(["env", "MYLA_B"]).output()))
    print(said(command(h).args(["env", "ONLY"]).env_clear().env("ONLY", "this").output()))
    print(said(command(h).args(["env", "MYLA_B"]).env_clear().output()))
    print(said(command("cmd").args(["/c", "cd"]).cwd("C:\\").output()))
    print(said(command(h).cwd("C:\\no\\such\\dir").output()))
    print(said(command(h).cwd("helper.exe").output()))
    print(said(run("no-such-program-anywhere", [])))
    print(said(run("./nothing.exe", [])))
    // a batch file by its name, through cmd: no `%` here, as Wine's cmd
    // reads `%%cd:~,%` otherwise than Windows' (the #test of std.platform's
    // `bat_command_line` pins it)
    print(said(run("echo-args", ["a b", "c&d", "x|y", ""])))
    match run(h, ["big", "300000"]) {
        Ok(o) => { print(f"big {o.stdout.len()} {o.stderr.len()}") },
        Err(e) => { print(f"error {e}") },
    }
    match command(h).args(["args", "piped"]).pipe(command(h).arg("cat")).output() {
        Ok(o) => { print(f"pipeline {bytes.to_str(o.second.stdout)}") },
        Err(e) => { print(f"error {e}") },
    }
    // a child's streams one line at a time, its end; a kill
    match command(h).arg("cat").spawn() {
        Ok(c) => {
            var child = c
            var w = match child.take_stdin() { Some(s) => s, None => panic("no input") }
            var lines = buffered(match child.take_stdout() { Some(s) => s, None => panic("no output") })
            let a = w.write(bytes.from_str("one\n"))
            print(f"line {line(lines.read_line())}")
            let b = w.write(bytes.from_str("two\n"))
            print(f"line {line(lines.read_line())}")
            let closed = w.close()
            print(f"end {line(lines.read_line())}")
            let st = child.wait()
            print(f"cat {status(st)}")
        }
        Err(e) => { print(f"error {e}") },
    }
    match command(h).args(["sleep", "5000"]).spawn() {
        Ok(c) => {
            var child = c
            print(f"id {child.id() > 0}")
            let before = child.try_wait()
            print(f"before {polled(before)}")
            let k = child.kill()
            print(f"kill {done(k)}")
            let st = child.wait()
            print(f"killed {status(st)}")
            let again = child.try_wait()
            print(f"again {polled(again)}")
            let k2 = child.kill()
            print(f"kill after {done(k2)}")
        }
        Err(e) => { print(f"error {e}") },
    }
}

#main
async fun main() {
    main_sync()
    // in a task: the others run while it waits
    async let ticks = ticking()
    print(said(await command("./helper.exe").arg("cat").stdin("through a task\n").output_async()))
    print(said(await run_async("./helper.exe", ["exit", "3"])))
    match command("./helper.exe").args(["sleep", "200"]).spawn() {
        Ok(c) => {
            var child = c
            let st = await child.wait_async()
            print(f"waited {status(st)}")
        }
        Err(e) => { print(f"error {e}") },
    }
    let n = await ticks
    print(f"ticked {n >= 5}")
}

async fun ticking() -> int {
    var n = 0
    for i in 0..10 {
        await task.sleep(20)
        n += 1
    }
    return n
}
"""

# Children waited for in tasks on many workers (MYLA-705 with MYLA-703's
# threads): 2 rounds of 200 children at once, each a task, its output read
# and its end awaited through the poller while other workers watch, forget
# and wake; it prints how many gave what they should (400).
MANY_CHILDREN = """import std.task as task
from std.process import run_async, command, ExitStatus
import std.bytes as bytes

// One child, its output read and its end awaited in a task: 1 when it gave
// what it should have.
async fun one(k: int) -> int {
    var want = f"{k}\\n"
    var r = await command("./helper.exe").arg("cat").stdin(want).output_async()
    if k % 3 == 0 {
        want = f"[{k}]\\n"
        r = await run_async("./helper.exe", ["args", f"{k}"])
    } else if k % 3 == 1 {
        want = ""
        r = await command("./helper.exe").args(["sleep", f"{k % 7 * 5}"]).output_async()
    }
    return match r {
        Ok(o) => if bytes.to_str(o.stdout) == want && o.status == ExitStatus.Exited(0) { 1 } else { 0 }
        Err(e) => 0
    }
}

#main
async fun main() {
    var ok = 0
    for round in 0..2 {
        var fs: [async () -> int] = []
        for k in 0..200 {
            fs.push(async () => await one(k))
        }
        for x in await task.all(fs) {
            ok += x
        }
    }
    print(ok)
}
"""

CHILDREN_OUT = (
    '[plain]\n[two words]\n[quo"te]\n[back\\slash]\n[tail\\]\n[]\n[\u00e9\u4e2d]\n[a\\\\"b]\n[\tx]\n||exit 0\n'
    "[found on PATH]\n||exit 0\n"
    "[with its extension]\n||exit 0\n"
    "||exit 70000\n"
    "||exit -2\n"
    "o|e|exit 0\n"
    "fed\nto it\n||exit 0\n"
    "set\n||exit 0\n"
    "none\n||exit 0\n"
    "kept\n||exit 0\n"
    "this\n||exit 0\n"
    "none\n||exit 0\n"
    "C:\\\r\n||exit 0\n"
    "error working directory not found\n"
    "error working directory is not a directory\n"
    "error program not found\n"
    "error program not found\n"
    '["a b"] ["c&d"] ["x|y"] [""]\r\n||exit 0\n'
    "big 300000 300000\n"
    "pipeline [piped]\n\n"
    "line one\nline two\nend <end>\ncat exit 0\n"
    "id true\nbefore running\nkill ok\nkilled exit 1\nagain exit 1\nkill after ok\n"
    "through a task\n||exit 0\n"
    "||exit 3\n"
    "waited exit 0\n"
    "ticked true\n"
)

# a recursion with no end (natively it runs out of stack long before n wraps)
DEEP = "fun deep(n: int) -> int {\n    if n == 0 { return 0 }\n    return deep(n + 1) + 1\n}\n\n"

# the entry's worker busy for good once it started a child: only another
# worker can run the child
BUSY_ENTRY = ("async fun main() {\n    async let a = child()\n    var i = 0\n"
              "    while i >= 0 {\n        i = (i + 1) % 7\n    }\n    print(await a)\n}\n")


def big_frame_program(main: str) -> str:
    """A program whose function `down` has a frame of 64 KiB (a struct of
    that size and its copy), recursing `n` deep, and then `main`."""
    levels = [("A", None, 8), ("B", "A", 8), ("C", "B", 8), ("D", "C", 16)]
    out = []
    for name, inner, n in levels:
        fields = ", ".join(f"f{i}: {inner or 'int64'}" for i in range(n))
        out.append(f"struct {name} {{ {fields} }}\n")
    for name, inner, n in levels:
        make = (lambda i: f"x + {i}") if inner is None else (lambda i, inner=inner: f"make_{inner.lower()}(x + {i})")
        vals = ", ".join(f"f{i}: {make(i)}" for i in range(n))
        out.append(f"fun make_{name.lower()}(x: int64) -> {name} {{\n    return {name} {{ {vals} }}\n}}\n")
    out.append("fun down(n: int, x: int64) -> int64 {\n    var d = make_d(x)\n    if n == 0 {\n        return d.f15.f7.f7.f7\n    }\n"
               "    d.f0.f0.f0.f0 = d.f15.f7.f7.f7 + 1\n    return down(n - 1, d.f0.f0.f0.f0) + 1\n}\n\n")
    return "".join(out) + main


def reserved_bytes(pid: int) -> int:
    """How much of the address space of the process `pid` is reserved with
    nothing behind it (Linux's `---p` mappings: under Wine, the reserved
    or decommitted part of a Windows process's mappings)."""
    total = 0
    with open(f"/proc/{pid}/maps", encoding="ascii") as fh:
        for line in fh:
            span, perms = line.split()[:2]
            if perms == "---p":
                lo, hi = (int(x, 16) for x in span.split("-"))
                total += hi - lo
    return total


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WINDOWS, WINDOWS_SKIP)
class Children(unittest.TestCase):
    """MYLA-705: std.process on `CreateProcessW` under Wine, with a Windows
    program of its own as the child (Linux's tools aren't on Windows' PATH):
    the arguments quoted so that the child's C runtime splits them back,
    the program found on PATH with PATHEXT's extensions (a batch file run by
    cmd, its arguments quoted for cmd), the exit code's 32 bits (D216), the
    streams as pipes, a text or nothing, the environment and the directory,
    the errors, waiting and killing (exit code 1), in a task too."""

    @classmethod
    def setUpClass(cls):
        wine_env()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def build(self, name: str, source: str) -> None:
        with open(os.path.join(self.tmp, name + ".my"), "w", encoding="utf-8") as fh:
            fh.write(source)
        argv = [selfhost_tool("main"), "build", name + ".my", "--target", "x86_64-windows", "--stdlib", STDLIB_ROOT,
                "-o", name + ".exe"]
        built = subprocess.run(argv, capture_output=True, text=True, cwd=self.tmp, timeout=300)
        self.assertEqual((built.stderr, built.returncode), ("", 0))

    def test_std_process_on_windows(self):
        self.build("helper", HELPER)
        self.build("prog", CHILDREN)
        with open(os.path.join(self.tmp, "echo-args.bat"), "w") as fh:
            fh.write("@echo [%1] [%2] [%3] [%4]\r\n")
        # the helper's directory on PATH: Wine makes a program's PATH of its
        # registry's and WINEPATH (drive Z: is the Unix root), Windows would
        # take PATH as it is
        env = dict(os.environ, WINEPATH="Z:" + self.tmp.replace("/", "\\"), MYLA_B="kept")
        ran = subprocess.run([*wine(), os.path.join(self.tmp, "prog.exe")], capture_output=True, cwd=self.tmp,
                             timeout=300, env=env)
        self.maxDiff = None
        self.assertEqual((ran.stdout.decode(), ran.stderr.decode(), ran.returncode), (CHILDREN_OUT, "", 0))

    def test_many_children_on_many_workers(self):
        # the poller watched, forgotten and woken by any worker while one
        # waits in it: on the merge of MYLA-703's threads with the poller's
        # first, lock-free block, a run in three on 4 workers crashed
        # (a grow freed the arrays a wait read)
        self.build("helper", HELPER)
        self.build("prog", MANY_CHILDREN)
        for threads in ["4", "4", "4", "4", "16"]:
            ran = subprocess.run([*wine(), os.path.join(self.tmp, "prog.exe")], capture_output=True, cwd=self.tmp,
                                 timeout=300, env=dict(os.environ, MYLA_THREADS=threads))
            self.assertEqual((ran.stdout, ran.returncode), (b"400\n", 0), f"{threads} workers: {ran.stderr[:300]!r}")

    def test_a_harness_runs_its_cases_as_children(self):
        # D217's `spawns` now true: `myla test --target x86_64-windows` runs
        # the harness once, which starts a child of itself for each case
        # (its scratch directory `c<k>`, where runs of the harness, MYLA-370,
        # have one for all), under Wine without Wine named again
        source = ('from std.process import exit, env\n\n'
                  '#test(1)[panic("boom")]\n#test(2)[2]\n#test(3)[panic("boom")]\n#test(4)[5]\n'
                  'fun f(x: int) -> int {\n    print(f"f {x}")\n    if x % 2 == 1 { panic("boom") }\n    return x\n}\n\n'
                  '#test()[exit(3)]\nfun g() {\n    print("g")\n    exit(3)\n}\n\n'
                  '#test\nfun last() {}\n\n'
                  '#test()["/c6"]\nfun case_dir() -> str {\n    let d = env("MYLA_TEST_DIR").unwrap_or("")\n'
                  '    return d[d.len() - 3:]\n}\n')
        with open(os.path.join(self.tmp, "t.my"), "w", encoding="utf-8") as fh:
            fh.write(source)
        env = dict(os.environ, MYLA_EMULATOR=" ".join(wine()))
        ran = subprocess.run([selfhost_tool("main"), "test", "t.my", "--target", "x86_64-windows", "--stdlib", STDLIB_ROOT],
                             capture_output=True, text=True, cwd=self.tmp, timeout=600, env=env)
        want = ("PASS  f #1\nPASS  f #2\nPASS  f #3\nFAIL  f #4: expected 5, got 4\n      | f 4\n"
                "PASS  g #1\nPASS  last\nPASS  case_dir #1\n\n6/7 passed.\n")
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (want, "", 1))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WINDOWS, WINDOWS_SKIP)
class Workers(unittest.TestCase):
    """MYLA-703 (D216, ending D221's one worker): the workers are threads
    (`CreateThread`), as many as MYLA_THREADS says, each with its state
    block in a TLS slot of its TEB; they park on WaitOnAddress; a stack
    overflow is reported as on Linux, on the main thread or a worker's; the
    heap's aligned mappings go back whole; std's concurrency stress programs
    print what they print on Linux."""

    setUpClass = HelloWorld.setUpClass
    setUp = HelloWorld.setUp
    build = HelloWorld.build
    build_and_run = HelloWorld.build_and_run

    def run_exe(self, *args: str, threads: str = "", timeout: float = 120) -> subprocess.CompletedProcess:
        env = dict(os.environ, MYLA_THREADS=threads) if threads else dict(os.environ)
        return subprocess.run([*wine(), os.path.join(self.tmp, "prog.exe"), *args], capture_output=True,
                              cwd=self.tmp, timeout=timeout, env=env)

    def test_a_stack_overflow_is_reported_as_on_linux(self):
        ran = self.build_and_run(DEEP + "fun main() {\n    print(deep(1))\n}\n")
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"", b"runtime error: stack overflow\n", 1))

    def test_a_workers_stack_overflow_too(self):
        # the child overflows on the second worker, the entry's busy
        built = self.build(DEEP + "async fun child() -> int {\n    return deep(1)\n}\n\n" + BUSY_ENTRY)
        self.assertEqual((built.stderr, built.returncode), ("", 0))
        ran = self.run_exe(threads="2", timeout=60)
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"", b"runtime error: stack overflow\n", 1))

    def test_as_many_workers_as_myla_threads_says(self):
        # two workers: the child runs beside the busy entry and ends the
        # program (D97); one: it never runs
        built = self.build("from std.process import exit\n\nasync fun child() -> int {\n    print(\"child\")\n"
                           "    exit(3)\n    return 0\n}\n\n" + BUSY_ENTRY)
        self.assertEqual((built.stderr, built.returncode), ("", 0))
        ran = self.run_exe(threads="2", timeout=60)
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"child\n", b"", 3))
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_exe(threads="1", timeout=3)

    @unittest.skipUnless(os.path.isdir("/proc/self"), "it reads Wine's mappings in /proc")
    def test_big_cells_go_back_whole_with_tasks(self):
        # a cell bigger than a chunk is a mapping of its own, aligned with
        # tasks: mapped larger, its ends given back, then the rest when it
        # is freed; the whole mapping goes back then (it stayed reserved:
        # 100 GiB more after 100 cells of 1 GiB)
        src = ('from std.io import stdin\n\n'
               'async fun churn(rounds: int) -> int {\n'
               '    var total = 0\n'
               '    var i = 0\n'
               '    while i < rounds {\n'
               '        var sb = StringBuilder(1073741824)\n'
               '        sb.append("x", 0, 1)\n'
               '        total += sb.build().len()\n'
               '        i += 1\n'
               '    }\n'
               '    return total\n'
               '}\n\n'
               'async fun main() {\n'
               '    var r = stdin()\n'
               '    async let first = churn(10)\n'
               '    print(await first)\n'
               '    let a = r.read_line()\n'
               '    async let second = churn(100)\n'
               '    print(await second)\n'
               '    let b = r.read_line()\n'
               '}\n')
        built = self.build(src)
        self.assertEqual((built.stderr, built.returncode), ("", 0))
        proc = subprocess.Popen([*wine(), os.path.join(self.tmp, "prog.exe")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, cwd=self.tmp)
        try:
            self.assertEqual(proc.stdout.readline(), b"10\n")
            before = reserved_bytes(proc.pid)
            proc.stdin.write(b"\n")
            proc.stdin.flush()
            self.assertEqual(proc.stdout.readline(), b"100\n")
            after = reserved_bytes(proc.pid)
            proc.stdin.write(b"\n")
            proc.stdin.close()
            self.assertEqual(proc.wait(timeout=60), 0)
        finally:
            proc.kill()
            proc.wait()
            proc.stdout.close()
        self.assertLess(after - before, 1 << 30, f"{(after - before) >> 20} MiB more reserved")

    def test_the_concurrency_stress_programs(self):
        # what they print on Linux, on 1, 4 and 16 workers (t27's children
        # are Linux's `echo`, which a Windows program can't start:
        # Children.test_many_children_on_many_workers is its ground there)
        from .test_concurrency_stress import _DIR, EXPECTED, EXPECTED_STDERR
        for name, (want_out, want_code) in sorted(EXPECTED.items()):
            if name == "t27_children_read_as_they_write":
                continue
            with self.subTest(program=name):
                with open(os.path.join(_DIR, name + ".my"), encoding="utf-8") as fh:
                    built = self.build(fh.read())
                self.assertEqual((built.stderr, built.returncode), ("", 0))
                for threads in ["1", "4", "16"]:
                    ran = self.run_exe(threads=threads, timeout=120)
                    got = (ran.stdout.decode(), ran.returncode)
                    self.assertEqual(got, (want_out, want_code), f"{threads} workers")
                    if name in EXPECTED_STDERR:
                        self.assertEqual(ran.stderr.decode(), EXPECTED_STDERR[name], f"{threads} workers")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class StackProbes(unittest.TestCase):
    """MYLA-717: Windows commits a thread's stack a page at a time below a
    guard page, so a prologue taking a page or more touches each page from
    the top down before it moves the stack pointer; Linux's is unchanged."""

    def asm(self, target: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "main.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(big_frame_program("fun main() {\n    print(down(100, 0))\n}\n"))
            return subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT, "--target", target],
                                  capture_output=True, text=True, check=True, timeout=300).stdout

    def test_a_frame_of_a_page_or_more_is_probed(self):
        lines = self.asm("x86_64-windows").split("\n")
        at = lines.index("myla_down:") + 1
        probes = []
        while lines[at].startswith("\torq $0, "):
            probes.append(lines[at])
            at += 1
        self.assertEqual(lines[at:at + 2], ["\tpushq %rbp", "\tmovq %rsp, %rbp"])
        frame = int(lines[at + 2].split("$")[1].split(",")[0])
        self.assertGreaterEqual(frame, 65536)
        # each page down to the lowest byte the push and the frame take
        bytes_taken = frame + 8
        want = [f"\torq $0, -{k}(%rsp)" for k in range(4096, bytes_taken, 4096)] + [f"\torq $0, -{bytes_taken}(%rsp)"]
        self.assertEqual(probes, want)

    def test_linux_has_none(self):
        lines = self.asm("x86_64-linux").split("\n")
        at = lines.index("myla_down:") + 1
        self.assertEqual(lines[at:at + 2], ["\tpushq %rbp", "\tmovq %rsp, %rbp"])


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(sys.platform == "win32", "Wine commits a thread's whole stack, so a frame past its guard page "
                     "works there anyway: MYLA-708's Windows runner runs this")
class FramesOnWindows(unittest.TestCase):
    """MYLA-717 on Windows itself: a recursion through a function with a
    64 KiB frame, on the main thread and on a worker, whose stacks Windows
    commits as they grow."""

    def test_a_recursion_through_a_64_kib_frame(self):
        main = ("async fun work() -> int64 {\n    return down(60, 0)\n}\n\n"
                "async fun main() {\n    async let a = work()\n    async let b = work()\n"
                "    print(down(100, 0))\n    print(await a + await b)\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "main.my"), "w", encoding="utf-8") as fh:
                fh.write(big_frame_program(main))
            subprocess.run([selfhost_tool("main"), "build", "main.my", "--target", "x86_64-windows", "--stdlib",
                            STDLIB_ROOT, "-o", "prog.exe"], cwd=tmp, check=True, timeout=300)
            ran = subprocess.run([os.path.join(tmp, "prog.exe")], capture_output=True, timeout=120,
                                 env=dict(os.environ, MYLA_THREADS="2"))
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"3836\n4632\n", b"", 0))


if __name__ == "__main__":
    unittest.main()
