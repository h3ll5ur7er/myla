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
and `FramesOnWindows`, which Windows itself runs on MYLA-708's runner,
`scripts/windows-runner.py`).

Files, directories and paths (MYLA-704): std.fs over kernel32 in UTF-16,
Windows' errors as Linux's causes where a program sees them, and std.path
on Windows' paths (`std/path_windows.my`, the loader's copy for the target).

Child processes (MYLA-705): `Children` runs std.process with a Windows
program of its own as the child, and a test harness's cases as children.

The console (MYLA-707): `Console` runs std.term and std.signal with a
pseudo-terminal as Wine's console and a Unix SIGINT as Ctrl-C;
`RUNNER_CASES` are what only Windows' own console shows (MYLA-708).

The bootstrap on Windows (MYLA-709): `HostScript` checks that
scripts/host.sh finds Windows and its seed, `BootstrapLink` that it builds a
stage by `myla build --target x86_64-windows`'s command lines.

Skipped where clang, llvm-dlltool, lld-link or Wine is missing (CI installs
them, and MYLA_REQUIRE_TARGETS makes a missing one fail there).
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import struct
import subprocess
import tempfile
import time
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


def coff_imports(path: str) -> dict[str, list[str]]:
    """The functions the PE file `path` imports, by DLL (lowercase), as
    `llvm-readobj --coff-imports` lists them (MYLA-722)."""
    listed = subprocess.run(["llvm-readobj", "--coff-imports", path], capture_output=True, text=True, check=True).stdout
    out: dict[str, list[str]] = {}
    dll = ""
    for line in listed.splitlines():
        words = line.split()
        if words[:1] == ["Name:"]:
            dll = words[1].lower()
            out[dll] = []
        elif words[:1] == ["Symbol:"]:
            out[dll].append(words[1])
    return out


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
        # (MYLA-722: WaitOnAddress is imported where the program parks, not
        # looked up at every start)
        self.assertEqual(list(coff_imports(os.path.join(self.tmp, "a.exe"))), ["kernel32.dll"])
        self.assertNotIn("GetProcAddress", coff_imports(os.path.join(self.tmp, "a.exe"))["kernel32.dll"])
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

    def test_a_socket_imports_winsock(self):
        # MYLA-706: sockets over ws2_32 (D212), which only a program that
        # opens one imports (Unsupported until then, D210)
        src = ('import std.net as net\n'
               'fun main() {\n'
               '    match net.udp_bind(net.parse_addr("127.0.0.1:0").expect("addr")) {\n'
               '        Ok(s) => { print("bound") },\n'
               '        Err(e) => { print(f"{e}") },\n'
               '    }\n'
               '}\n')
        ran = self.build_and_run(src)
        self.assertEqual((ran.stdout, ran.returncode), (b"bound\n", 0))
        self.assertIn("ws2_32.dll", pe_facts(os.path.join(self.tmp, "prog.exe"))["dlls"])

    def test_an_import_library_per_dll(self):
        # MYLA-722: random bytes from bcrypt (D212), the workers' parking
        # from the API set of WaitOnAddress, each DLL's import library made
        # of the functions the program calls of it (the code generator's
        # `windows_dll`), none left beside the program; one that calls only
        # kernel32's functions imports only kernel32 (the hello world above)
        src = ('import std.uuid as uuid\n'
               'import std.random as random\n'
               'async fun twice(n: int) -> int {\n    return 2 * n\n}\n'
               'async fun main() {\n'
               '    let a = f"{uuid.v4()}"\n'
               '    let b = f"{uuid.v4()}"\n'
               '    print(a.len() == 36 && a[14] == \'4\' && a != b)\n'
               '    var r = random.from_os()\n'
               '    var seen: [int: bool] = [:]\n'
               '    for i in 0..100 { seen[r.int_in(0, 1000000)] = true }\n'
               '    print(seen.len() > 90)\n'
               '    async let x = twice(21)\n'
               '    print(await x)\n'
               '}\n')
        built = self.build(src)
        self.assertEqual((built.stderr, built.returncode), ("", 0))
        self.assertEqual(sorted(os.listdir(self.tmp)), ["main.my", "prog.exe"])
        exe = os.path.join(self.tmp, "prog.exe")
        self.assertEqual(pe_facts(exe)["dlls"], ["kernel32.dll", "bcrypt.dll", "api-ms-win-core-synch-l1-2-0.dll"])
        imports = coff_imports(exe)
        self.assertEqual(imports["bcrypt.dll"], ["BCryptGenRandom"])
        self.assertEqual(sorted(imports["api-ms-win-core-synch-l1-2-0.dll"]), ["WaitOnAddress", "WakeByAddressSingle"])
        self.assertNotIn("GetProcAddress", imports["kernel32.dll"])
        ran = self.run_exe()
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"true\ntrue\n42\n", b"", 0))

    def test_temporary_files_and_directories(self):
        # MYLA-722: their random names, under %TEMP% (D227)
        src = ('import std.fs as fs\n'
               'from std.process import env\n'
               'fun main() {\n'
               '    let root = env("TEMP").unwrap_or("")\n'
               '    let d = fs.make_temp_dir().expect("dir")\n'
               '    let e = fs.make_temp_dir().expect("dir")\n'
               '    print(root != "" && d.starts_with(root + "\\\\myla-") && d.len() == root.len() + 22 && d != e)\n'
               '    print(fs.is_dir(d))\n'
               '    let (p, file) = fs.make_temp_file().expect("file")\n    var f = file\n'
               '    let c = f.close()\n'
               '    print(fs.is_file(p) && p.starts_with(root + "\\\\myla-"))\n'
               '    for x in [d, e] { fs.remove_dir(x).expect("rmdir") }\n'
               '    fs.remove_file(p).expect("rm")\n'
               '    print(fs.exists(d) || fs.exists(p))\n'
               '}\n')
        ran = self.build_and_run(src)
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"true\ntrue\ntrue\nfalse\n", b"", 0))

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


# MYLA-717's recursion through the 64 KiB frame on the main thread, 100 deep,
# and in two tasks, 60 deep each, with MYLA_THREADS=2, and what it prints
# (`FramesOnWindows` under Wine, scripts/windows-runner.py on Windows, MYLA-708)
FRAMES = big_frame_program("async fun work() -> int64 {\n    return down(60, 0)\n}\n\n"
                           "async fun main() {\n    async let a = work()\n    async let b = work()\n"
                           "    print(down(100, 0))\n    print(await a + await b)\n}\n")
FRAMES_OUT = b"3836\n4632\n"


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
        source = ('from std.process import exit, env\nimport std.test as test\nimport std.fs as fs\n\n'
                  '#test(1)[panic("boom")]\n#test(2)[2]\n#test(3)[panic("boom")]\n#test(4)[5]\n'
                  'fun f(x: int) -> int {\n    print(f"f {x}")\n    if x % 2 == 1 { panic("boom") }\n    return x\n}\n\n'
                  '#test()[exit(3)]\nfun g() {\n    print("g")\n    exit(3)\n}\n\n'
                  '#test\nfun last() {}\n\n'
                  '#test()["\\\\c6"]\nfun case_dir() -> str {\n    let d = env("MYLA_TEST_DIR").unwrap_or("")\n'
                  '    return d[d.len() - 3:]\n}\n\n'
                  # MYLA-728: under %TEMP%, not /tmp (Wine's is on C:, not Z:)
                  '#test()[true]\nfun under_temp() -> bool {\n    let d = env("MYLA_TEST_DIR").unwrap_or("")\n'
                  '    let t = env("TEMP").unwrap_or("?")\n'
                  '    return d.starts_with(t + "\\\\myla-test-") && !d.starts_with("Z:")\n}\n\n'
                  '#test\nfun a_temp_dir() {\n    let d = test.temp_dir()\n    test.expect(fs.is_dir(d))\n'
                  '    test.expect(d.starts_with(env("MYLA_TEST_DIR").unwrap_or("?")))\n'
                  '    test.expect(fs.write_to_file(d + "\\\\f.txt", "x").is_ok())\n}\n')
        with open(os.path.join(self.tmp, "t.my"), "w", encoding="utf-8") as fh:
            fh.write(source)
        env = dict(os.environ, MYLA_EMULATOR=" ".join(wine()))
        ran = subprocess.run([selfhost_tool("main"), "test", "t.my", "--target", "x86_64-windows", "--stdlib", STDLIB_ROOT],
                             capture_output=True, text=True, cwd=self.tmp, timeout=600, env=env)
        want = ("PASS  f #1\nPASS  f #2\nPASS  f #3\nFAIL  f #4: expected 5, got 4\n      | f 4\n"
                "PASS  g #1\nPASS  last\nPASS  case_dir #1\nPASS  under_temp #1\nPASS  a_temp_dir\n\n8/9 passed.\n")
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (want, "", 1))


# What `Sockets` runs (MYLA-706): many connections echoed through loopback,
# each a pair of tasks, beside children and an HTTP server of the program's
# own that answers its own client (the helper's `cat` as the children).
SOCKETS = r"""import std.task as task
import std.net as net
import std.http as http
import std.bytes as bytes
from std.net import TcpListener, TcpStream
from std.http import Request, Response
from std.process import command, args, exit, ExitStatus
from std.io import eprintln

// MYLA-706: many sockets at once on the I/O completion port, beside
// children: `clients` connections echoed through loopback, each its own
// pair of tasks, while `kids` children echo their input and an HTTP server
// in this program answers its own client. What fails says so on stderr,
// and the program then ends with 1, or with 2 once 200 s have gone
// (naming the tasks that hadn't ended), rather than waiting for ever for a
// server whose client gave up (MYLA-753: CI's runner saw only "still
// running").

// One connection served: what it sends echoed until its end.
async fun echo(s: TcpStream) -> int {
    var c = s
    var total = 0
    while true {
        let chunk = match await c.read_async(65536) {
            Ok(b) => b
            Err(e) => { return -1 }
        }
        if chunk.len() == 0 {
            break
        }
        match await c.write_async(chunk) {
            Ok(n) => { total += n }
            Err(e) => { return -2 }
        }
    }
    let gone = c.close()
    return total
}

// `n` connections accepted, each echoed in a task of its own: the bytes
// echoed.
async fun serve(l: TcpListener, n: int) -> int {
    var fs: [async () -> int] = []
    for k in 0..n {
        let s = match await l.accept_async() {
            Ok(s) => s
            Err(e) => { return -1 }
        }
        fs.push(async () => await echo(s))
    }
    var total = 0
    for x in await task.all(fs) {
        if x < 0 {
            return x
        }
        total += x
    }
    return total
}

// A client: `rounds` messages of `size` bytes sent and read back: 1 when
// all came back as sent.
async fun client(port: int, k: int, rounds: int, size: int) -> int {
    var s = match await net.connect_async(net.addr(net.loopback(), port)) {
        Ok(s) => s
        Err(e) => { return failed(f"client {k}: connect: {e}") }
    }
    var msg: [uint8] = []
    for i in 0..size {
        msg.push(97u8 + ((i + k) % 26) as uint8)
    }
    for r in 0..rounds {
        match await s.write_async(msg) {
            Ok(_) => {}
            Err(e) => { return failed(f"client {k}: write {r}: {e}") }
        }
        var got: [uint8] = []
        while got.len() < size {
            match await s.read_async(size - got.len()) {
                Ok(b) => {
                    if b.len() == 0 {
                        return failed(f"client {k}: the end after {got.len()} of {size} bytes")
                    }
                    for x in b {
                        got.push(x)
                    }
                }
                Err(e) => { return failed(f"client {k}: read {r}: {e}") }
            }
        }
        if got != msg {
            return failed(f"client {k}: round {r} came back changed")
        }
    }
    let c = s.close()
    return 1
}

// A child echoing its input (the helper's `cat`): 1 when it gave it back.
async fun kid(k: int) -> int {
    let want = f"child {k}\n"
    return match await command("./helper.exe").arg("cat").stdin(want).output_async() {
        Ok(o) => if bytes.to_str(o.stdout) == want && o.status == ExitStatus.Exited(0) { 1 } else { failed(f"child {k}: {bytes.to_str(o.stdout)}") }
        Err(e) => failed(f"child {k}: {e}")
    }
}

fun handle(r: Request) -> Response {
    return http.response(200, f"hello {r.method} {r.path()}")
}

// Its own HTTP server asked `n` times: the answers that were right.
async fun ask(port: int, n: int) -> int {
    var c = http.client()
    var right = 0
    for i in 0..n {
        match await c.get_async(f"http://127.0.0.1:{port}/p{i}") {
            Ok(r) => {
                if r.status == 200 && r.text() == f"hello GET /p{i}" {
                    right += 1
                } else {
                    let no = failed(f"ask {i}: {r.status} {r.text()}")
                }
            }
            Err(e) => {
                let no = failed(f"ask {i}: {e}")
            }
        }
    }
    c.close()
    return right
}

// `what` on stderr: 0, a task's failure.
fun failed(what: str) -> int {
    eprintln(what)
    return 0
}

// Which of the program's tasks have ended, for a run that takes too long.
actor Progress {
    ended: [bool],
}

impl Progress {
    fun end(var self, k: int) {
        self.ended[k] = true
    }

    fun pending(self) -> str {
        var sb = StringBuilder()
        var k = 0
        for e in self.ended {
            if !e {
                sb.append(f" {k}")
            }
            k += 1
        }
        return sb.build()
    }
}

// `x`, once task `k` is marked ended.
async fun ended_as(p: Progress, k: int, x: int) -> int {
    await p.end(k)
    return x
}

// `serve`, at most 200 s.
async fun serve_within(l: TcpListener, n: int) -> int {
    return match await task.timeout(200000, async () => await serve(l, n)) {
        Some(x) => x
        None => failed("the echo server: still serving after 200 s") - 3
    }
}

// `http.serve_n`, at most 200 s: how many requests it answered, or -1.
async fun http_within(l: TcpListener, n: int) -> int {
    return match await task.timeout(200000, async () => await http.serve_n(l, n, handle)) {
        Some(Ok(k)) => k
        Some(Err(e)) => failed(f"the HTTP server: {e}") - 1
        None => failed("the HTTP server: still serving after 200 s") - 1
    }
}

fun number(s: str) -> int {
    var n = 0
    for c in s {
        n = n * 10 + (c - '0')
    }
    return n
}

#main
async fun main() {
    let a = args()
    let clients = number(a[1])
    let kids = number(a[2])
    var l = match net.listen_with(net.addr(net.loopback(), 0), 1024) {
        Ok(l) => l
        Err(e) => { panic(f"listen: {e}") }
    }
    let port = match l.local_addr() {
        Ok(x) => x.port
        Err(e) => { panic("addr") }
    }
    var hl = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic(f"listen: {e}") }
    }
    let hport = match hl.local_addr() {
        Ok(x) => x.port
        Err(e) => { panic("addr") }
    }
    async let served = serve_within(l, clients)
    async let answered = http_within(hl, 20)
    // tasks 0 to clients - 1 the clients, then the children, then `ask`
    var ended: [bool] = []
    for k in 0..clients + kids + 1 {
        ended.push(false)
    }
    let progress = Progress { ended: ended }
    var fs: [async () -> int] = []
    for k in 0..clients {
        // small messages, and every tenth one past what a socket buffers
        var size = 100 + k
        if k % 10 == 0 {
            size = 300000
        }
        fs.push(async () => await ended_as(progress, k, await client(port, k, 3, size)))
    }
    for k in 0..kids {
        fs.push(async () => await ended_as(progress, clients + k, await kid(k)))
    }
    fs.push(async () => await ended_as(progress, clients + kids, await ask(hport, 20)))
    let all = async () => await task.all(fs)
    var results: [int] = []
    match await task.timeout(200000, all) {
        Some(xs) => { results = xs }
        None => {
            eprintln(f"still running after 200 s, tasks:{await progress.pending()}")
            exit(2)
        }
    }
    var ok = 0
    for x in results {
        ok += x
    }
    if ok != clients + kids + 20 {
        // (a server whose client gave up would wait for it for ever)
        eprintln(f"{ok} of {clients + kids + 20} right")
        exit(1)
    }
    let echoed = await served
    let http_served = await answered
    let c1 = l.close()
    let c2 = hl.close()
    print(f"{ok - 20} of {clients + kids} right, http {http_served}, echoed {echoed > 0}")
}
"""

# A socket closed while its last send still goes on: the peer gets every
# byte, then the end (MYLA-706's `ws_close_later`; without it the reader
# got 3,919,872 of the 4,000,000 bytes).
CLOSED_WHILE_SENDING = r"""import std.task as task
import std.net as net
from std.net import TcpListener, TcpStream

// A socket closed while its last send still goes on: the peer still gets
// every byte, then the end (MYLA-706's `ws_close_later`).
async fun server(l: TcpListener, n: int) -> int {
    var s = match await l.accept_async() {
        Ok(s) => s
        Err(e) => { return -1 }
    }
    var big: [uint8] = []
    for i in 0..n {
        big.push(97u8 + (i % 26) as uint8)
    }
    let w = match await s.write_async(big) {
        Ok(k) => k
        Err(e) => -2
    }
    let c = s.close()
    return w
}

async fun client(port: int) -> int {
    var s = match await net.connect_async(net.addr(net.loopback(), port)) {
        Ok(s) => s
        Err(e) => { return -1 }
    }
    // let the server write and close before reading anything
    await task.sleep(300)
    var total = 0
    while true {
        match await s.read_async(65536) {
            Ok(b) => {
                if b.len() == 0 {
                    break
                }
                total += b.len()
            }
            Err(e) => { return -2 }
        }
    }
    let c = s.close()
    return total
}

#main
async fun main() {
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("listen") }
    }
    let port = match l.local_addr() {
        Ok(x) => x.port
        Err(e) => { panic("addr") }
    }
    for round in 0..3 {
        async let wrote = server(l, 4000000)
        async let read = client(port)
        let a = await wrote
        let b = await read
        print(f"{a} {b}")
    }
}
"""

# MYLA-726: a child's input written by one task while another reads its
# output, more than the pipes hold, so each waits for the other: on one
# worker only `write_async` suspending its task lets the reader run (std.
# process's own `input_written_while_output_read` with a Windows `cat`).
INPUT_WHILE_OUTPUT = r"""import std.task as task
from std.process import command, Child, ChildStdin, ChildStdout, ExitStatus
from std.io import buffered

// MYLA-726: a child's input written by one task while another reads its
// output, more than the pipes hold, so each waits for the other: on one
// worker only `write_async` lets the reader run.
async fun feed(w: ChildStdin, rounds: int, n: int) -> int {
    var inp = w
    var piece: [uint8] = []
    for i in 0..n {
        piece.push(97u8 + (i % 26) as uint8)
    }
    piece.push(10u8)
    var total = 0
    for k in 0..rounds {
        match await inp.write_async(piece) {
            Ok(m) => { total += m }
            Err(e) => { return -1 }
        }
    }
    match inp.close() {
        Ok(_) => {}
        Err(e) => { return -2 }
    }
    return total
}

async fun drink(r: ChildStdout) -> int {
    var out = buffered(r)
    return match await out.read_to_end_async() {
        Ok(s) => s.len()
        Err(e) => -1
    }
}

#main
async fun main() {
    var child = match command("./helper.exe").arg("cat").spawn() {
        Ok(c) => c
        Err(e) => { panic(f"spawn: {e}") }
    }
    let w = child.take_stdin().expect("stdin")
    let r = child.take_stdout().expect("stdout")
    async let wrote = feed(w, 10, 59999)
    async let got = drink(r)
    let a = await wrote
    let b = await got
    let st = match child.wait() {
        Ok(ExitStatus.Exited(c)) => c
        _ => -1
    }
    print(f"{a} {b} {st}")
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WINDOWS, WINDOWS_SKIP)
class Sockets(unittest.TestCase):
    """MYLA-706: sockets over Winsock and the poller on an I/O completion
    port: TCP through loopback, many connections at once beside children
    and an HTTP exchange within the program, on 1, 4 and 16 workers; a
    close that waits for its send; and MYLA-726, a child's input pipe
    written through the port, so `write_async` suspends its task."""

    setUpClass = Children.setUpClass
    setUp = Children.setUp
    build = Children.build

    def run_exe(self, *args: str, threads: str, timeout: float = 120) -> subprocess.CompletedProcess:
        return subprocess.run([*wine(), os.path.join(self.tmp, "prog.exe"), *args], capture_output=True,
                              cwd=self.tmp, timeout=timeout, env=dict(os.environ, MYLA_THREADS=threads))

    def test_many_sockets_and_children_at_once(self):
        self.build("helper", HELPER)
        self.build("prog", SOCKETS)
        for threads in ["1", "4", "16"]:
            ran = self.run_exe("200", "50", threads=threads)
            self.assertEqual((ran.stdout, ran.stderr, ran.returncode),
                             (b"250 of 250 right, http 20, echoed true\n", b"", 0), f"{threads} workers")

    def test_a_close_waits_for_its_send(self):
        self.build("prog", CLOSED_WHILE_SENDING)
        for threads in ["1", "4"]:
            ran = self.run_exe(threads=threads)
            self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"4000000 4000000\n" * 3, b"", 0),
                             f"{threads} workers")

    def test_a_childs_input_written_while_its_output_is_read(self):
        # at BASE (9738e37) one worker never ended (`timeout 30`: 124)
        self.build("helper", HELPER)
        self.build("prog", INPUT_WHILE_OUTPUT)
        for threads in ["1", "2", "4"]:
            ran = self.run_exe(threads=threads, timeout=60)
            self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"600000 600000 0\n", b"", 0),
                             f"{threads} workers")


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
@unittest.skipUnless(HAVE_WINDOWS, WINDOWS_SKIP)
class FramesOnWindows(unittest.TestCase):
    """MYLA-717: a recursion through a function with a 64 KiB frame, on the
    main thread and on a worker. Wine commits a thread's whole stack, so a
    frame past its guard page works here anyway: this shows the program
    right, and Windows itself, which commits a stack as it grows, runs it on
    MYLA-708's runner (`scripts/windows-runner.py`'s `frames/64-kib`)."""

    setUpClass = HelloWorld.setUpClass
    setUp = HelloWorld.setUp
    build = HelloWorld.build
    run_exe = Workers.run_exe

    def test_a_recursion_through_a_64_kib_frame(self):
        built = self.build(FRAMES)
        self.assertEqual((built.stderr, built.returncode), ("", 0))
        ran = self.run_exe(threads="2")
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (FRAMES_OUT, b"", 0))


_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_HOST_SH = os.path.join(_REPO, "scripts", "host.sh")


def host_sh(script: str, env: dict | None = None, cwd: str | None = None) -> subprocess.CompletedProcess:
    """`script` run by bash after sourcing scripts/host.sh, with `env` added
    to this process's environment."""
    return subprocess.run(["bash", "-c", f'. "{_HOST_SH}"\n{script}'], capture_output=True, text=True,
                          env={**os.environ, **(env or {})}, cwd=cwd or _REPO, timeout=300)


class HostScript(unittest.TestCase):
    """MYLA-709: scripts/host.sh finds Windows by Git Bash's `uname -s`
    (MSYS2's `MINGW64_NT-…`, `MSYS_NT-…`; `MYLA_OS` in its place here), takes
    the Windows seed there and names its programs `.exe`; Linux is as it was."""

    def facts(self, **env: str) -> str:
        done = host_sh('echo "$HOST_OS $HOST_TARGET $HOST_SEED [$EXE]"', {"AS": "true", "LD": "true",
                                                                        "DLLTOOL": "true", **env})
        return (done.stdout + done.stderr).strip()

    def test_each_machine_its_seed(self):
        self.assertEqual(self.facts(MYLA_OS="Linux", MYLA_ARCH="x86_64"), "linux x86_64-linux bootstrap/seed.s []")
        self.assertEqual(self.facts(MYLA_OS="Linux", MYLA_ARCH="aarch64"),
                         "linux aarch64-linux bootstrap/seed-aarch64.s []")
        for name in ("MINGW64_NT-10.0-20348", "MSYS_NT-10.0-20348", "windows"):
            self.assertEqual(self.facts(MYLA_OS=name, MYLA_ARCH="x86_64"),
                             "windows x86_64-windows bootstrap/seed-windows.s [.exe]", name)
        self.assertIn("the Windows seed is x86_64's", self.facts(MYLA_OS="windows", MYLA_ARCH="aarch64"))
        self.assertIn("macOS is MYLA-164", self.facts(MYLA_OS="Darwin"))

    def test_every_seed_is_committed(self):
        done = host_sh('for e in $SEEDS; do echo "${e#*:}"; done', {"AS": "true", "LD": "true"})
        seeds = done.stdout.split()
        self.assertIn("bootstrap/seed-windows.s", seeds)
        for seed in seeds:
            self.assertTrue(os.path.isfile(os.path.join(_REPO, seed)), seed)


_STUB = """#!/bin/sh
# {name} as the test runs it: its command line logged, the files it reads kept
printf '%s\\n' "{name} $*" >> "$STUB_LOG"
for a in "$@"; do
    case "$a" in *.s | *.def) cp "$a" "$STUB_KEEP/" ;; esac
done
exec "{real}" "$@"
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WINDOWS, WINDOWS_SKIP)
class BootstrapLink(unittest.TestCase):
    """MYLA-709: the bootstrap on Windows assembles and links each stage as
    `myla build --target x86_64-windows` does (scripts/host.sh's
    `windows_asm_to_bin`, selfhost/driver.my's `cmd_build`): the same
    command lines of clang, llvm-dlltool and lld-link, the same import lists,
    read from the assembly's `# import` lines, and a program that runs."""

    setUpClass = HelloWorld.setUpClass

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        stubs = os.path.join(self.tmp, "stubs")
        os.mkdir(stubs)
        for name in TOOLS:
            path = os.path.join(stubs, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_STUB.format(name=name, real=shutil.which(name)))
            os.chmod(path, 0o755)
        self.path = stubs + os.pathsep + os.environ.get("PATH", "")

    def logged(self, where: str, argv: list[str], env: dict | None = None) -> tuple[list[str], dict]:
        """The tools' command lines when `argv` runs in `where` (made), and
        the import lists they read, by name."""
        keep = os.path.join(where, "keep")
        os.makedirs(keep)
        log = os.path.join(where, "log")
        done = subprocess.run(argv, capture_output=True, text=True, cwd=where, timeout=300,
                              env={**os.environ, **(env or {}), "PATH": self.path, "STUB_LOG": log, "STUB_KEEP": keep})
        self.assertEqual((done.stderr, done.returncode), ("", 0))
        with open(log, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        defs = {}
        for name in sorted(os.listdir(keep)):
            if name.endswith(".def"):
                with open(os.path.join(keep, name), encoding="utf-8") as fh:
                    defs[name] = fh.read()
        return lines, defs

    def test_the_same_steps_as_myla_build(self):
        src = os.path.join(self.tmp, "main.my")
        with open(src, "w", encoding="utf-8") as fh:
            # three DLLs: kernel32, bcrypt (std.random) and the synch API set (tasks)
            fh.write('import std.random as random\n'
                     'async fun twice(n: int) -> int {\n    return 2 * n\n}\n'
                     'async fun main() {\n'
                     '    var r = random.from_os()\n'
                     '    let n = r.int_in(0, 10)\n'
                     '    async let x = twice(21)\n'
                     '    print(f"{await x} {n >= 0 && n < 10}")\n'
                     '}\n')
        built = os.path.join(self.tmp, "built")
        os.mkdir(built)
        by_myla, defs_myla = self.logged(built, [selfhost_tool("main"), "build", src, "--target", "x86_64-windows",
                                                 "--stdlib", STDLIB_ROOT, "-o", "prog.exe"])
        self.assertEqual([line.split()[0] for line in by_myla], ["clang", "llvm-dlltool", "llvm-dlltool",
                                                                  "llvm-dlltool", "lld-link"])
        # the assembly myla build assembled, built again by the bootstrap's steps
        booted = os.path.join(self.tmp, "booted")
        os.mkdir(booted)
        shutil.copy(os.path.join(built, "keep", "prog.exe.s"), booted)
        by_host, defs_host = self.logged(booted, ["bash", "-c", f'. "{_HOST_SH}"; asm_to_bin prog.exe.s prog.exe'],
                                         {"MYLA_OS": "windows", "MYLA_ARCH": "x86_64"})
        self.assertEqual(by_host, by_myla)
        self.assertEqual(defs_host, defs_myla)
        self.assertEqual(list(defs_host), ["prog.exe.api-ms-win-core-synch-l1-2-0.def", "prog.exe.bcrypt.def",
                                           "prog.exe.kernel32.def"])
        ran = subprocess.run([*wine(), os.path.join(booted, "prog.exe")], capture_output=True, timeout=120)
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), (b"42 true\n", b"", 0))


# MYLA-723: what a program run on the machine the tools run on reads of the
# standard library's modules that a target has copies of
HOST_PATHS = ('import std.path as path\nimport std.platform as platform\nimport std.path_style as style\n\n'
              'fun main() {\n    print(path.parent("a\\\\b").unwrap_or("none"))\n    print(platform.TARGET)\n'
              '    print(style.WINDOWS)\n}\n')
HOST_TESTS = ('import std.path as path\nimport std.test as test\nfrom std.process import env\n\n'
              '#test("a\\\\b")[Some("a")]\nfun up(p: str) -> Option<str> {\n    return path.parent(p)\n}\n\n'
              # MYLA-729: the interpreter's case root under %TEMP%, joined with `\`
              '#test()[true]\nfun under_temp() -> bool {\n    let d = test.temp_dir()\n'
              '    return d.starts_with(env("TEMP").unwrap_or("?") + "\\\\myla-test-")\n}\n')
# what only Windows' std.platform declares: checked against Linux's, an error
HOST_CHECKED = 'import std.platform as platform\n\nfun never() {\n    platform.windows_start()\n}\n\nfun main() {}\n'


# A client of the language server for HostModules: myla-lsp.exe as its
# child, open.txt's messages sent, the first diagnostics printed, then
# close.txt's sent
LSP_CLIENT = '''from std.process import command
from std.io import buffered
import std.bytes as bytes
import std.fs as fs
import std.num as num

fun main() {
    var child = match command("./myla-lsp.exe").spawn() {
        Ok(c) => c
        Err(e) => panic(f"spawn: {e}")
    }
    var w = match child.take_stdin() { Some(s) => s, None => panic("no input") }
    var r = buffered(match child.take_stdout() { Some(s) => s, None => panic("no output") })
    let sent = w.write(bytes.from_str(fs.read_to_string("open.txt").unwrap_or("")))
    while true {
        var length = 0
        while true {
            let line = match r.read_line() {
                Ok(Some(l)) => l
                _ => panic("the server ended")
            }
            if line == "\\r" || line == "" { break }
            if line.starts_with("Content-Length: ") {
                length = num.parse_int(line[16:line.len() - 1]).unwrap_or(0) as int
            }
        }
        let body = match r.read_exact(length) {
            Ok(Some(b)) => b
            _ => panic("the server ended")
        }
        if body.contains("publishDiagnostics") {
            print(body)
            break
        }
    }
    let closing = w.write(bytes.from_str(fs.read_to_string("close.txt").unwrap_or("")))
    let closed = w.close()
    let x = child.wait()
}
'''


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WINDOWS, WINDOWS_SKIP)
class HostModules(unittest.TestCase):
    """MYLA-723: a `myla.exe` built for Windows runs, tests, checks and
    serves a program with Windows' own std.platform, std.path and
    std.path_style (the loader's `for_host`), as a native build for Windows
    takes them (`for_target`); a module of the library named as the entry is
    itself all the same (`myla test lib/std/path.my` runs path.my's cases).
    MYLA-729: its interpreter's case root is under `%TEMP%`."""

    @classmethod
    def setUpClass(cls):
        wine_env()
        cls.tmp = tempfile.mkdtemp()
        for exe, src in (("myla.exe", "selfhost/main.my"), ("myla-lsp.exe", "tools/lsp/main.my")):
            subprocess.run([selfhost_tool("main"), "build", src, "--target", "x86_64-windows", "--stdlib", STDLIB_ROOT,
                            "-o", os.path.join(cls.tmp, exe)], cwd=_REPO, check=True, timeout=600)
        for name, text in (("p.my", HOST_PATHS), ("t.my", HOST_TESTS), ("c.my", HOST_CHECKED)):
            with open(os.path.join(cls.tmp, name), "w", encoding="utf-8") as fh:
                fh.write(text)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def myla(self, *args: str, stdin: bytes = b"", cwd: str | None = None, exe: str = "myla.exe"):
        ran = subprocess.run([*wine(), os.path.join(self.tmp, exe), *args], input=stdin, capture_output=True,
                             cwd=cwd or self.tmp, timeout=600)
        return ran.stdout.decode(), ran.stderr.decode(), ran.returncode

    def test_run(self):
        self.assertEqual(self.myla("run", "p.my"), ("a\nx86_64-windows\ntrue\n", "", 0))

    def test_test_interpreted(self):
        self.assertEqual(self.myla("test", "t.my"), ("PASS  up #1\nPASS  under_temp #1\n\n2/2 passed.\n", "", 0))

    def test_check(self):
        self.assertEqual(self.myla("check", "c.my"), ("ok\n", "", 0))

    def test_repl(self):
        out, err, code = self.myla("repl", stdin=b'import std.path as path\npath.parent("a\\\\b")\n')
        self.assertEqual((out, err, code), ('Some("a")\n', "myla> myla> myla> \n", 0))

    def test_the_language_server(self):
        # driven by a Windows program of its own: the server waits for its
        # input to pause before it checks (`ready`), which under Wine a Linux
        # parent's pipe never shows (MYLA-708)
        def frame(m: dict) -> str:
            body = json.dumps(m)
            return f"Content-Length: {len(body.encode())}\r\n\r\n{body}"
        uri = "file:///c.my"
        with open(os.path.join(self.tmp, "open.txt"), "w", encoding="utf-8", newline="") as fh:
            fh.write(frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}})
                     + frame({"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {"textDocument": {
                         "uri": uri, "languageId": "myla", "version": 1, "text": HOST_CHECKED}}}))
        with open(os.path.join(self.tmp, "close.txt"), "w", encoding="utf-8", newline="") as fh:
            fh.write(frame({"jsonrpc": "2.0", "id": 2, "method": "shutdown"}) + frame({"jsonrpc": "2.0", "method": "exit"}))
        with open(os.path.join(self.tmp, "client.my"), "w", encoding="utf-8") as fh:
            fh.write(LSP_CLIENT)
        subprocess.run([selfhost_tool("main"), "build", "client.my", "--target", "x86_64-windows", "--stdlib",
                        STDLIB_ROOT, "-o", "client.exe"], cwd=self.tmp, check=True, timeout=300)
        out, err, code = self.myla(exe="client.exe")
        self.assertEqual((err, code), ("", 0))
        got = json.loads(out)
        self.assertEqual(got["method"], "textDocument/publishDiagnostics")
        self.assertEqual(got["params"], {"uri": uri, "diagnostics": []})

    def test_a_native_harness_is_built_under_temp(self):
        # MYLA-729: under %TEMP%, joined with `\`; Wine has no LLVM for
        # Windows, so the build fails and the harness is kept, its path in
        # the message (Windows' runner builds and runs it: tools/myla-build)
        with open(os.path.join(self.tmp, "sq.my"), "w", encoding="utf-8") as fh:
            fh.write("#test(2)[4]\nfun sq(x: int) -> int {\n    return x * x\n}\n")
        out, err, code = self.myla("test", "sq.my", "--native")
        self.assertEqual((out, code), ("", 1))
        import re
        kept = re.search(r"\(kept at (C:\\users\\[^\\]+\\Temp\\myla-test-\d+)\\harness\.exe\.my\)\n$", err)
        self.assertIsNotNone(kept, err)
        unix = os.path.join(os.environ["WINEPREFIX"], "drive_c", *kept.group(1)[3:].split("\\"))
        self.assertTrue(os.path.isfile(os.path.join(unix, "harness.exe.my")))
        shutil.rmtree(unix)

    def test_a_module_of_the_library_named_is_itself(self):
        # path.my's own cases (Linux's rules), not its Windows copy's
        linux = subprocess.run([selfhost_tool("main"), "test", "lib/std/path.my", "--stdlib", "lib"],
                               capture_output=True, text=True, cwd=_REPO, timeout=600)
        self.assertEqual((linux.stderr, linux.returncode), ("", 0))
        self.assertEqual(self.myla("test", "lib/std/path.my", "--stdlib", "lib", cwd=_REPO), (linux.stdout, "", 0))


# MYLA-707: the console as std.term's terminal and std.signal's signals.
# One program, its first argument the case; `mode(fd)` is the console mode
# `__term_get` keeps for the descriptor (D216's saved mode, 4 bytes).
CONSOLE = """import std.term as term
import std.signal as signal
import std.task as task
import std.process as process
import std.io as io
import std.fs as fs
import std.num as num
import std.bytes as bytes
from std.term import Key, Stream
from std.signal import Signal
from std.process import Stdio, ExitStatus
from std.ioerror import IoError

fun down(n: int) -> int {
    return down(n + 1) + 1
}

async fun fails() -> int {
    await task.sleep(10)
    panic("a task failed")
}

#allow(primitive)
fun mode(fd: int) -> int {
    let m = __term_get(fd)
    if m.len() != 4 {
        return -1
    }
    return (m[0] as int) | ((m[1] as int) << 8)
}

fun raw() -> term.RawMode {
    return match term.raw_mode() {
        Ok(r) => r
        Err(e) => panic(f"raw_mode: {e}")
    }
}

fun name(k: Key) -> str {
    return match k {
        Key.Char(c) => f"Char({c})"
        Key.Ctrl(c) => f"Ctrl({c})"
        Key.Alt(c) => f"Alt({c})"
        Key.Up => "Up"
        Key.Enter => "Enter"
        Key.Escape => "Escape"
        Key.Delete => "Delete"
        Key.F(n) => f"F{n}"
        _ => "another key"
    }
}

fun code_of(st: Result<ExitStatus, IoError>) -> str {
    return match st {
        Ok(Exited(c)) => f"{c}"
        Ok(Signaled(s)) => f"signal {s}"
        Err(e) => f"{e}"
    }
}

// the console's input raw, `count` keys read, the mode back, a line read
fun read_keys(count: int) {
    let before = mode(0)
    let r = raw()
    let m = mode(0)
    print(f"raw line {m & 2} echo {m & 4} processed {m & 1} vt {m & 512}")
    var kr = term.key_reader()
    var n = 0
    while n < count {
        match kr.next() {
            Ok(Some(k)) => print(f"key {name(k)}")
            Ok(None) => print("end")
            Err(e) => print(f"error: {e}")
        }
        n += 1
    }
    match r.restore() {
        Ok(()) => print(f"restored {mode(0) == before}")
        Err(e) => print(f"restore: {e}")
    }
    var input = io.stdin()
    match input.read_line() {
        Ok(Some(line)) => print(f"line {line}")
        _ => print("no line")
    }
}

// raw mode ended as `how` says (D187)
#allow(primitive)
async fun end(how: str) {
    let r = raw()
    if how == "nested" {
        let inner = raw()
        let x = inner.restore()
        panic("after the inner one")
    }
    if how == "left" {
        // raw mode left, then raw again behind the hook's back: it stays
        let m = __term_get(0)
        let x = r.restore()
        let s = __term_set(0, m)
        return
    }
    if how == "exit" {
        process.exit(3)
    }
    if how == "panic" {
        panic("boom")
    }
    let n = process.args().len()
    if how == "index" {
        let xs = [1]
        print(xs[n])
    }
    if how == "key" {
        let m: [int: int] = [:]
        print(m[n])
    }
    if how == "deep" {
        print(down(n))
    }
    if how == "fails" {
        async let a = fails()
        print(await a)
    }
}

// each end of raw mode in a child on this console: its status, and whether
// the console's mode is what it was
fun ends() {
    for how in ["return", "exit", "panic", "index", "key", "deep", "nested", "fails", "left"] {
        let before = mode(0)
        let cmd = process.command(process.args()[0]).arg("end").arg(how).stdin_from(Stdio.Inherit)
        var child = match cmd.stdout_from(Stdio.Null).stderr_from(Stdio.Null).spawn() {
            Ok(c) => c
            Err(e) => panic(f"spawn: {e}")
        }
        print(f"{how} {code_of(child.wait())} restored {mode(0) == before}")
    }
}

// raw mode until a Ctrl-C ends the program (D192), with a listener first
// that takes one (`listen`)
async fun wait(how: str) {
    let r = raw()
    if how == "listen" {
        let s = match signal.listen() {
            Ok(s) => s
            Err(e) => panic(f"listen: {e}")
        }
        print("listening")
        match await s.next() {
            Ok(sig) => print(f"caught {sig}")
            Err(e) => print(f"{e}")
        }
        s.close()
    }
    print("raw")
    await task.sleep(30000)
    print("not here")
}

// `wait` in a child on this console (its last argument `c` and the token),
// its lines passed on, then its status and whether the console's mode is
// what it was; this program listening meanwhile, as a console's Ctrl-C or
// Ctrl-Break reaches every program on it
fun ctrl(how: str, token: str) {
    let s = match signal.listen() {
        Ok(s) => s
        Err(e) => panic(f"listen: {e}")
    }
    let before = mode(0)
    let cmd = process.command(process.args()[0]).arg("wait").arg(how).arg("c" + token).stdin_from(Stdio.Inherit)
    var child = match cmd.stderr_from(Stdio.Inherit).spawn() {
        Ok(c) => c
        Err(e) => panic(f"spawn: {e}")
    }
    var out = match child.take_stdout() {
        Some(o) => io.buffered(o)
        None => panic("no output")
    }
    var more = true
    while more {
        match out.read_line() {
            Ok(Some(l)) => print(f"child {l}")
            _ => { more = false }
        }
    }
    print(f"exited {code_of(child.wait())} restored {mode(0) == before}")
    s.close()
}

// the console's output mode, escape sequences turned on by a child, and
// the mode again once it ended
fun vt() {
    let before = mode(1)
    let cmd = process.command(process.args()[0]).arg("ansi").stdin_from(Stdio.Inherit)
    var child = match cmd.stdout_from(Stdio.Inherit).stderr_from(Stdio.Inherit).spawn() {
        Ok(c) => c
        Err(e) => panic(f"spawn: {e}")
    }
    let st = code_of(child.wait())
    print(f"vt:{(before & 4) == 0},{st},{mode(1) == before}")
}

fun ansi() {
    print(f"ansi:{term.enable_ansi(Stream.Stdout)},{(mode(1) & 4) != 0}")
}

async fun ticker() -> int {
    var n = 0
    while !task.cancelled() {
        var k = 0
        while k < 10000 {
            k += 1
        }
        await task.sleep(1)
        n += 1
    }
    return n
}

// Ctrl-C after Ctrl-C to a listener while tasks keep the workers busy,
// then the default again
async fun storm(want: int) {
    let s = match signal.listen() {
        Ok(s) => s
        Err(e) => panic(f"listen: {e}")
    }
    async let a = ticker()
    async let b = ticker()
    async let c = ticker()
    print("ready")
    var n = 0
    var other = 0
    while n < want && other == 0 {
        match await s.next() {
            Ok(Interrupt) => { n += 1 }
            Ok(Terminate) => { other += 1 }
            Err(e) => { other += 1 }
        }
    }
    print(f"got {n} interrupts, {other} else")
    task.cancel(a)
    task.cancel(b)
    task.cancel(c)
    print(f"ticked {await a > 0 && await b > 0 && await c > 0}")
    s.close()
    print("default again")
    await task.sleep(30000)
    print("not here")
}

// the size of the console each stream is
fun sizes() {
    for (label, s) in [("stdin", Stream.Stdin), ("stdout", Stream.Stdout), ("stderr", Stream.Stderr)] {
        match term.size_of(s) {
            Some((c, r)) => print(f"{label} {c} {r}")
            None => print(f"{label} none")
        }
    }
}

// the first interrupt or termination, then the default again
async fun interrupted() {
    print("ready")
    match await signal.interrupted() {
        Ok(sig) => print(f"got {sig}")
        Err(e) => print(f"error: {e}")
    }
    print("again")
    await task.sleep(30000)
    print("not here")
}

async fun catch_one(s: signal.Signals) -> int {
    match await s.next() {
        Ok(sig) => print(f"caught {sig}")
        Err(e) => print(f"{e}")
    }
    return 0
}

// a line read from the console while a listener takes a Ctrl-C (which
// ends the console's read on Windows: it goes on)
async fun read_line_listening() {
    let s = match signal.listen() {
        Ok(s) => s
        Err(e) => panic(f"listen: {e}")
    }
    async let c = catch_one(s)
    print("ready")
    var input = io.stdin()
    match input.read_line() {
        Ok(Some(line)) => print(f"line {line}")
        Ok(None) => print("end")
        Err(e) => print(f"error: {e}")
    }
    let x = await c
}

// three lines of the console, read with reads of at most 1, 3 and 64
// bytes, each read's bytes shown (a CR as `\\r`, a LF as `\\n`) (MYLA-734)
fun pieces() {
    var input = io.fd_stream(0)
    for size in [1, 3, 64] {
        print(f"ready {size}")
        var shown = ""
        var more = true
        while more {
            match input.read(size) {
                Ok(b) => {
                    let t = bytes.to_str(b)
                    shown = shown + "[" + t.replace("\\r", "\\\\r").replace("\\n", "\\\\n") + "]"
                    more = b.len() > 0 && !t.contains("\\n")
                }
                Err(e) => {
                    shown = shown + f"error {e}"
                    more = false
                }
            }
        }
        print(f"{size}: {shown}")
    }
}

// the first signal written to the file `path` after "ready", then the exit
// with 7: what a program does with the time Windows gives it once its
// console is closed
async fun on_close(path: str) {
    let s = match signal.listen() {
        Ok(s) => s
        Err(e) => panic(f"listen: {e}")
    }
    let w = fs.write_to_file(path, "ready\\n")
    match await s.next() {
        Ok(sig) => { let w2 = fs.write_to_file(path, f"ready\\ngot {sig}\\n") }
        Err(e) => { let w2 = fs.write_to_file(path, f"ready\\n{e}\\n") }
    }
    process.exit(7)
}

#main
async fun main() {
    let args = process.args()
    let case = args[1]
    if case == "keys" { read_keys(num.parse_int(args[2]).unwrap_or(0) as int) }
    if case == "size" { sizes() }
    if case == "interrupted" { await interrupted() }
    if case == "readline" { await read_line_listening() }
    if case == "pieces" { pieces() }
    if case == "close" { await on_close(args[2]) }
    if case == "end" { await end(args[2]) }
    if case == "ends" { ends() }
    if case == "wait" { await wait(args[2]) }
    if case == "ctrl" { ctrl(args[2], args[3]) }
    if case == "vt" { vt() }
    if case == "ansi" { ansi() }
    if case == "storm" { await storm(10) }
}
"""


def unix_pids_with(word: str) -> list[int]:
    """The processes whose command line has `word` (Wine's processes have
    their Windows command line)."""
    pids = []
    for entry in os.listdir("/proc"):
        if entry.isdecimal():
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as fh:
                    words = fh.read().replace(b"\0", b" ").split()
            except OSError:
                continue
            if word.encode() in words:
                pids.append(int(entry))
    return pids


def cpu_seconds(pids: list[int]) -> float:
    """The CPU seconds the processes `pids` used so far, every thread's
    (`/proc/<pid>/stat`'s utime and stime); a process gone counts none."""
    total = 0
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat", encoding="ascii") as fh:
                fields = fh.read().rsplit(")", 1)[1].split()
        except OSError:
            continue
        total += int(fields[11]) + int(fields[12])
    return total / os.sysconf("SC_CLK_TCK")


def wine_server_pids() -> list[int]:
    """The processes of the Wine server of this process's prefix."""
    pids = []
    for entry in os.listdir("/proc"):
        if entry.isdecimal():
            try:
                with open(f"/proc/{entry}/comm", encoding="utf-8") as fh:
                    if not fh.read().startswith("wineserver"):
                        continue
                with open(f"/proc/{entry}/environ", "rb") as fh:
                    env = fh.read().split(b"\0")
            except OSError:
                continue
            if ("WINEPREFIX=" + os.environ.get("WINEPREFIX", "")).encode() in env:
                pids.append(int(entry))
    return pids


class ConsolePty:
    """A Windows program under Wine with a pseudo-terminal, which Wine makes
    its console, as its standard input (and its output too, `all_streams`),
    its output's lines read as they come."""

    def __init__(self, argv: list[str], env: dict | None = None, all_streams: bool = False):
        # (Unix's modules: the file is imported on Windows too, for
        # FramesOnWindows)
        import fcntl
        import pty
        import termios
        self.master, self.slave = pty.openpty()
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 33, 101, 0, 0))
        out = self.slave if all_streams else subprocess.PIPE
        self.proc = subprocess.Popen([*wine(), *argv], stdin=self.slave, stdout=out, stderr=out, env=env,
                                     start_new_session=True)
        self.all_streams = all_streams
        self.buf = b""

    def _more(self, timeout: float) -> bool:
        import select
        src = self.master if self.all_streams else self.proc.stdout.fileno()
        r, _, _ = select.select([src], [], [], timeout)
        if not r:
            return False
        try:
            chunk = os.read(src, 65536)
        except OSError:
            return False
        self.buf += chunk
        if self.all_streams:
            # Wine's console draws on a terminal: it hides the cursor around
            # a write and ends a line with CR CR LF
            self.buf = self.buf.replace(b"\x1b[?25l", b"").replace(b"\x1b[?25h", b"").replace(b"\r\r\n", b"\n")
        return bool(chunk)

    def line(self, timeout: float = 60) -> str:
        """The next line of the output, without its newline ("" at its end)."""
        deadline = time.time() + timeout
        while b"\n" not in self.buf and time.time() < deadline:
            if not self._more(0.1) and self.proc.poll() is not None and not self._more(0.1):
                break
        if b"\n" not in self.buf:
            rest, self.buf = self.buf, b""
            return rest.decode("utf-8", "replace")
        got, self.buf = self.buf.split(b"\n", 1)
        return got.decode("utf-8", "replace")

    def send(self, data: bytes):
        os.write(self.master, data)

    def finish(self, timeout: float = 60) -> tuple[list[str], int]:
        """The rest of the output's lines and the exit status."""
        deadline = time.time() + timeout
        while self.proc.poll() is None and time.time() < deadline:
            self._more(0.1)
        while self._more(0.1):
            pass
        if self.proc.poll() is None:
            self.proc.kill()
        code = self.proc.wait()
        lines = self.buf.decode("utf-8", "replace").split("\n")
        if lines[-1] == "":
            lines.pop()
        self.close()
        return lines, code

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        for f in (self.proc.stdout, self.proc.stderr):
            if f:
                f.close()
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WINDOWS, WINDOWS_SKIP)
class Console(unittest.TestCase):
    """MYLA-707 (D216) under Wine, whose console is a pseudo-terminal this
    side opens: the console as a terminal, raw mode on its input mode, the
    mode back at every end of a program (D187) and on a Ctrl-C while raw
    (D192), Ctrl-C (a Unix SIGINT to Wine, which makes it a CTRL_C_EVENT on
    a thread of its own) as std.signal's interrupt on 1, 4 and 16 workers,
    a listener waiting without the CPU (MYLA-744), and the output mode put
    back at the exit. A program sharing the console
    with its child reads the mode the child left, as the console outlives
    the child. What Wine can't show is MYLA-708's runner's (`RUNNER_CASES`)."""

    @classmethod
    def setUpClass(cls):
        wine_env()
        cls.tmp = tempfile.mkdtemp()
        with open(os.path.join(cls.tmp, "console.my"), "w", encoding="utf-8") as fh:
            fh.write(CONSOLE)
        cls.exe = os.path.join(cls.tmp, "console.exe")
        subprocess.run([selfhost_tool("main"), "build", "console.my", "--target", "x86_64-windows", "--stdlib",
                        STDLIB_ROOT, "-o", cls.exe], cwd=cls.tmp, check=True, timeout=300)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def start(self, *args: str, threads: str = "2", all_streams: bool = False) -> ConsolePty:
        p = ConsolePty([self.exe, *args], env=dict(os.environ, MYLA_THREADS=threads), all_streams=all_streams)
        self.addCleanup(p.close)
        return p

    def test_the_console_is_a_terminal(self):
        # stdin the console, stdout and stderr pipes; the input's size is its
        # screen buffer's (`CONOUT$`), whatever Wine makes it
        src = ("import std.term as term\nfrom std.term import Stream\n\nfun main() {\n"
               "    print(f\"tty {term.is_tty(Stream.Stdin)} {term.is_tty(Stream.Stdout)} "
               "{term.is_tty(Stream.Stderr)}\")\n"
               "    match term.size() {\n        Some((c, r)) => print(f\"size {c > 0 && r > 0}\")\n"
               "        None => print(\"no size\")\n    }\n"
               "    print(f\"ansi {term.enable_ansi(Stream.Stdout)} {term.enable_ansi(Stream.Stdin)}\")\n}\n")
        with open(os.path.join(self.tmp, "tty.my"), "w", encoding="utf-8") as fh:
            fh.write(src)
        subprocess.run([selfhost_tool("main"), "build", "tty.my", "--target", "x86_64-windows", "--stdlib",
                        STDLIB_ROOT, "-o", "tty.exe"], cwd=self.tmp, check=True, timeout=300)
        p = ConsolePty([os.path.join(self.tmp, "tty.exe")])
        self.addCleanup(p.close)
        self.assertEqual(p.finish(), (["tty true false false", "size true", "ansi false true"], 0))

    def test_raw_mode_and_back(self):
        p = self.start("keys", "3")
        self.assertEqual(p.line(), "raw line 0 echo 0 processed 0 vt 512")
        for key in [b"q", b"x", b"\r"]:
            p.send(key)
            time.sleep(0.2)
        self.assertEqual([p.line() for _ in range(4)], ["key Char(q)", "key Char(x)", "key Enter", "restored true"])
        # cooked again: a line, whose CR LF the console's read gives as
        # "\n" (MYLA-734)
        p.send(b"hello\r")
        self.assertEqual(p.finish(), (["line hello"], 0))

    def test_every_end_restores_the_console(self):
        lines, code = self.start("ends", threads="4").finish(timeout=120)
        self.assertEqual((lines, code), (["return 0 restored true", "exit 3 restored true",
                                          "panic 1 restored true", "index 1 restored true",
                                          "key 1 restored true", "deep 1 restored true",
                                          "nested 1 restored true", "fails 1 restored true",
                                          "left 0 restored false"], 0))

    def ctrl_c(self, word: str):
        """A Ctrl-C to the child whose command line has `word` (its parent's
        has it without the `c`)."""
        pids = unix_pids_with("c" + word)
        self.assertEqual(len(pids), 1, pids)
        os.kill(pids[0], signal.SIGINT)

    def test_a_ctrl_c_while_raw_puts_the_mode_back(self):
        # D192: on a thread Windows makes, without a state block (D222);
        # Windows' default then ends the child (STATUS_CONTROL_C_EXIT;
        # Wine's exit code 0)
        for threads in ["1", "4", "16"]:
            for how in ["raw", "listen"]:
                with self.subTest(threads=threads, how=how):
                    token = f"t{os.getpid()}{threads}{how}"
                    p = self.start("ctrl", how, token, threads=threads)
                    if how == "listen":
                        self.assertEqual(p.line(), "child listening")
                        time.sleep(0.2)
                        self.ctrl_c(token)
                        self.assertEqual(p.line(), "child caught interrupt")
                    self.assertEqual(p.line(), "child raw")
                    time.sleep(0.2)
                    self.ctrl_c(token)
                    lines, code = p.finish(timeout=30)
                    self.assertIn(lines, [["exited 0 restored true"], ["exited -1073741510 restored true"]])
                    self.assertEqual(code, 0)

    def test_ctrl_c_after_ctrl_c_on_many_workers(self):
        for threads in ["1", "4", "16"]:
            with self.subTest(threads=threads):
                p = self.start("storm", threads=threads)
                self.assertEqual(p.line(), "ready")
                for _ in range(10):
                    time.sleep(0.1)
                    p.proc.send_signal(signal.SIGINT)
                self.assertEqual([p.line() for _ in range(3)],
                                 ["got 10 interrupts, 0 else", "ticked true", "default again"])
                time.sleep(0.2)
                start = time.time()
                p.proc.send_signal(signal.SIGINT)
                lines, code = p.finish(timeout=20)
                # ended by the Ctrl-C (Wine's default handler: exit code 0)
                self.assertEqual((lines, code), ([], 0))
                self.assertLess(time.time() - start, 10)

    def test_the_output_mode_is_put_back_at_the_exit(self):
        # the child turns escape sequences on (`enable_ansi`) on the console
        # it shares with this program, which finds its mode as before
        lines, code = self.start("vt", all_streams=True).finish()
        self.assertEqual((lines, code), (["ansi:true,true", "vt:true,0,true"], 0))

    def test_interrupted_and_the_default_again(self):
        p = self.start("interrupted")
        self.assertEqual(p.line(), "ready")
        time.sleep(0.2)
        p.proc.send_signal(signal.SIGINT)
        self.assertEqual([p.line(), p.line()], ["got interrupt", "again"])
        time.sleep(0.2)
        p.proc.send_signal(signal.SIGINT)
        self.assertEqual(p.finish(timeout=20), ([], 0))

    def test_a_listener_alone_uses_no_cpu(self):
        # MYLA-744: the console's control handler posts a packet to the
        # poller's port, which waits for it without a time limit; it looked
        # at the signals' pipe each millisecond (Wine's server too: each
        # wait's end is a request of its)
        server = wine_server_pids()
        for threads in ["1", "4", "16"]:
            with self.subTest(threads=threads):
                p = self.start("interrupted", threads=threads)
                self.assertEqual(p.line(), "ready")
                time.sleep(0.5)
                before = cpu_seconds([p.proc.pid, *server])
                time.sleep(2)
                used = cpu_seconds([p.proc.pid, *server]) - before
                p.proc.send_signal(signal.SIGINT)
                self.assertEqual([p.line(), p.line()], ["got interrupt", "again"])
                time.sleep(0.2)
                p.proc.send_signal(signal.SIGINT)
                self.assertEqual(p.finish(timeout=20), ([], 0))
                # CPU seconds in 2 s of waiting: about none
                self.assertLess(used, 0.05, f"{used:.2f} s of CPU in 2 s waiting for a signal")

    def test_a_read_of_the_console_while_a_listener_takes_a_ctrl_c(self):
        p = self.start("readline")
        self.assertEqual(p.line(), "ready")
        time.sleep(0.2)
        p.proc.send_signal(signal.SIGINT)
        self.assertEqual(p.line(), "caught interrupt")
        p.send(b"hello\r")
        self.assertEqual(p.finish(), (["line hello"], 0))

    def test_a_line_of_the_console_read_in_pieces(self):
        # MYLA-734: the console's CR LF is "\n" however the reads cut the
        # line, the CR at a full read's end too (its LF the next read's)
        p = self.start("pieces")
        got = []
        for size in ("1", "3", "64"):
            self.assertEqual(p.line(), f"ready {size}")
            time.sleep(0.2)  # (Wine's console drops a line typed before the read)
            p.send(b"hello\r")
            got.append(p.line())
        self.assertEqual(got, ["1: [h][e][l][l][o][\\n]", "3: [hel][lo][\\n]", "64: [hello\\n]"])
        self.assertEqual(p.finish(), ([], 0))

    def test_the_time_a_signal_leaves(self):
        # `close`'s program with a Ctrl-C: Wine's console can't be closed
        # under a program (MYLA-708's runner closes Windows' own)
        path = os.path.join(self.tmp, "closed.txt")
        p = self.start("close", path)
        deadline = time.time() + 60
        while not os.path.exists(path) and time.time() < deadline:
            time.sleep(0.05)
        time.sleep(0.2)
        p.proc.send_signal(signal.SIGINT)
        self.assertEqual(p.finish(), ([], 7))
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "ready\ngot interrupt\n")

    def test_the_sizes_without_a_console(self):
        lines, code = self.start("size").finish()
        # (stdin: Wine's console, whose screen buffer isn't the terminal's)
        self.assertEqual((lines[1:], code), (["stdout none", "stderr none"], 0))
        self.assertRegex(lines[0], r"^stdin \d+ \d+$")


# A case of std.platform's Windows module that only Windows runs (its own
# cases run on the host too, interpreted and natively): a Ctrl-C to a
# console of the case's own (`AllocConsole`, after leaving any it shares,
# so no other process gets it) while it listens; how many the console's
# control handler counted (`__win_console_cp`'s word that `read` tells a
# read of lines a Ctrl-C ended by, MYLA-708) and what it wrote to the
# signals' pipe, which it does after counting.
CTRL_COUNTED = '''
#test()[(1, 2)]
fun ctrl_counted() -> (int64, int64) {
    let left = __syscall(__rt_get("__imp_FreeConsole"), 0, 0, 0)
    let made = __syscall(__rt_get("__imp_AllocConsole"), 0, 0, 0)
    let h = signal_listen(1)
    let before = __load_acq64(__rt_addr("__win_console_cp") + CTRLS_TAKEN)
    let sent = __syscall(__rt_get("__imp_GenerateConsoleCtrlEvent"), 0, 0, 0)
    let sig = signal_take(h)
    let counted = __load_acq64(__rt_addr("__win_console_cp") + CTRLS_TAKEN) - before
    let off = signal_listen(0)
    let freed = __syscall(__rt_get("__imp_FreeConsole"), 0, 0, 0)
    return (counted, sig)
}
'''


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WINDOWS, WINDOWS_SKIP)
class ControlHandler(unittest.TestCase):
    """MYLA-708: Windows gives a read of the console's lines that a Ctrl-C
    ended 0 bytes and no error, which `read` tells from the end by the
    control handler's count of Ctrl-Cs and Ctrl-Breaks. Wine doesn't end
    the read (the runner's terminal/06-readline does that part); this is
    the count, `CTRL_COUNTED` appended to a copy of the library's module."""

    setUpClass = HelloWorld.setUpClass

    def test_the_handler_counts_a_ctrl_c(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(os.path.join(STDLIB_ROOT, "std"), os.path.join(tmp, "std"))
            module = os.path.join(tmp, "std", "platform_windows.my")
            with open(module, "a", encoding="utf-8") as fh:
                fh.write(CTRL_COUNTED)
            ran = subprocess.run([selfhost_tool("main"), "test", module, "--target", "x86_64-windows", "--stdlib", tmp,
                                  "--only", "ctrl_counted"], capture_output=True, text=True, timeout=600,
                                 env=dict(os.environ, MYLA_EMULATOR=" ".join(wine())))
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), ("PASS  ctrl_counted #1\n\n1/1 passed.\n", "", 0))


# MYLA-753, a case of std.platform's Windows module that only Windows runs:
# more packets queued on the port than one `GetQueuedCompletionStatusEx`
# takes (ENTRIES, 64), as under load, where every arm posts one and every
# operation's end another. 200 handles ready (signalled events, watched
# as a child's end is) armed, a wake-up among them: one wait with no time
# limit gives every one of them, each once, and the wake-up. With one
# batch a wait (BASE `983fcc3`) it gave 64, and the rest waited for later
# waits behind whatever was queued after them: under load a connection's
# request waited past the HTTP server's 5 s and was dropped.
POLLER_DRAINS = '''
#test()[(200, 200, 0)]
fun poller_drains() -> (int64, int64, int64) {
    let p = poller_new()
    var events: [int64] = []
    var k: int64 = 0
    while k < 200 {
        // manual reset, signalled
        let ev = __syscall5(__rt_get("__imp_CreateEventW"), 0, 1, 1, 0, 0)
        events.push(ev)
        let ws = ws_new(ev, K_PROCESS, false)
        let armed = ws_watch(ev, 1, k + 1)
        if k == 100 {
            poller_wake(p)
        }
        k += 1
    }
    let got = poller_wait(p, 0)
    var seen: [bool] = []
    while seen.len() <= 200 {
        seen.push(false)
    }
    var distinct: int64 = 0
    var i: int64 = 0
    while i < got {
        let tok = __load64(__load64(p + 16) + 8 * i)
        if tok >= 1 && tok <= 200 && !seen[tok as int] {
            seen[tok as int] = true
            distinct += 1
        }
        i += 1
    }
    // nothing left: the next wait ends with no event and no wake-up due
    let again = poller_wait(p, 0)
    for ev in events {
        let c = __syscall(__rt_get("__imp_CloseHandle"), ev, 0, 0)
    }
    return (got, distinct, again + __load64(net() + NET_WAKE))
}
'''


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WINDOWS, WINDOWS_SKIP)
class PollerBacklog(unittest.TestCase):
    """MYLA-753: a wait takes every packet queued on the port, not one batch,
    so a handle ready now isn't left behind a backlog (`POLLER_DRAINS`,
    appended to a copy of the library's module)."""

    setUpClass = HelloWorld.setUpClass

    def test_a_wait_takes_the_whole_backlog(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(os.path.join(STDLIB_ROOT, "std"), os.path.join(tmp, "std"))
            module = os.path.join(tmp, "std", "platform_windows.my")
            with open(module, "a", encoding="utf-8") as fh:
                fh.write(POLLER_DRAINS)
            ran = subprocess.run([selfhost_tool("main"), "test", module, "--target", "x86_64-windows", "--stdlib", tmp,
                                  "--only", "poller_drains"], capture_output=True, text=True, timeout=600,
                                 env=dict(os.environ, MYLA_EMULATOR=" ".join(wine())))
        self.assertEqual((ran.stdout, ran.stderr, ran.returncode), ("PASS  poller_drains #1\n\n1/1 passed.\n", "", 0))


# MYLA-707's cases for MYLA-708's Windows runner, what Wine's console can't
# show: each runs CONSOLE built as `console.exe` with its arguments in a
# console of its own, its input that console and its output a file, as
# `cmd /c "console.exe ARGS > out.txt"` started with CREATE_NEW_CONSOLE
# gives (`close` writes its file itself and runs as `console.exe` alone,
# so that its status is its own). `before` sets the console up (in the
# same cmd line, with `&&`); each step of `steps` waits for the output
# to have its text (`wait`), puts input events into the console's input
# (`keys`: WriteConsoleInputW on CONIN$ from a process attached to the
# console, `AttachConsole`; a name is that key pressed and let go, "x"
# the character, "Ctrl-c" with LEFT_CTRL_PRESSED, "Alt-x" with
# LEFT_ALT_PRESSED), sends a console control event to every process on
# the console (`event`: GenerateConsoleCtrlEvent(event, 0) from the
# attached process, which ignores them itself with
# SetConsoleCtrlHandler(NULL, TRUE)) or closes the console's window
# (`close`: WM_CLOSE to GetConsoleWindow()'s window, which is
# CTRL_CLOSE_EVENT). `out` is the file's text at the end and `exit` the
# status of `cmd` (that of console.exe), within `seconds`. The runner
# names console.exe by its whole path, so that it finds itself when it
# starts itself as a child (MYLA-708). With `"host": "pty"` the console is
# a pseudo console (ConPTY) instead: `keys` are typed into it as a
# terminal types them (a Ctrl-C is ETX, which the pseudo console makes a
# real Ctrl-C: keys written with WriteConsoleInputW never are, conhost's
# input buffer takes them as they are), and `close` is ClosePseudoConsole
# (CTRL_CLOSE_EVENT without a window to close).
STATUS_CONTROL_C_EXIT = 0xC000013A
RUNNER_CASES = [
    {"name": "raw keys from a real console, escape sequences through ENABLE_VIRTUAL_TERMINAL_INPUT",
     "args": ["keys", "8"],
     "steps": [{"wait": "raw line 0 echo 0 processed 0 vt 512\n"},
               {"keys": ["Up", "Ctrl-c", "q", "Alt-x", "F5", "Delete", "Escape", "Enter"]},
               {"wait": "restored true\n"},
               {"keys": ["h", "e", "l", "l", "o", "Enter"]}],
     "out": "raw line 0 echo 0 processed 0 vt 512\nkey Up\nkey Ctrl(c)\nkey Char(q)\nkey Alt(x)\nkey F5\n"
            "key Delete\nkey Escape\nkey Enter\nrestored true\nline hello\n",
     "exit": 0, "seconds": 30},
    {"name": "UTF-8 typed into a cooked read (the console's input code page 65001)",
     "args": ["keys", "1"],
     "steps": [{"wait": "raw line"}, {"keys": ["x"]}, {"wait": "restored true\n"},
               {"keys": ["g", "r", "ö", "ß", "e", "Enter"]}],
     "out": "raw line 0 echo 0 processed 0 vt 512\nkey Char(x)\nrestored true\nline größe\n",
     "exit": 0, "seconds": 30},
    {"name": "the window's size, through each stream that is the console (stdout is the file)",
     "args": ["size"], "before": "mode con: cols=101 lines=33", "steps": [],
     "out": "stdin 101 33\nstdout none\nstderr 101 33\n", "exit": 0, "seconds": 30},
    {"name": "a real Ctrl-C to a listener, then the default: STATUS_CONTROL_C_EXIT",
     "args": ["interrupted"],
     "steps": [{"wait": "ready\n"}, {"event": "CTRL_C_EVENT"}, {"wait": "again\n"}, {"event": "CTRL_C_EVENT"}],
     "out": "ready\ngot interrupt\nagain\n", "exit": STATUS_CONTROL_C_EXIT, "seconds": 30},
    {"name": "Ctrl-Break is an interrupt too",
     "args": ["interrupted"],
     "steps": [{"wait": "ready\n"}, {"event": "CTRL_BREAK_EVENT"}, {"wait": "again\n"}, {"event": "CTRL_BREAK_EVENT"}],
     "out": "ready\ngot interrupt\nagain\n", "exit": STATUS_CONTROL_C_EXIT, "seconds": 30},
    {"name": "Ctrl-C typed while a cooked read of the console waits: the read goes on (ERROR_OPERATION_ABORTED)",
     "args": ["readline"], "host": "pty",
     "steps": [{"wait": "ready\n"}, {"keys": ["Ctrl-c"]}, {"wait": "caught interrupt\n"},
               {"keys": ["h", "i", "Enter"]}],
     "out": "ready\ncaught interrupt\nline hi\n", "exit": 0, "seconds": 30},
    {"name": "the console closed: Terminate, and the program's own exit within Windows' 5 seconds",
     "args": ["close", "closed.txt"], "alone": True, "host": "pty",
     "steps": [{"wait_file": "closed.txt", "text": "ready\n"}, {"close": True}],
     "file": "ready\ngot terminate\n", "exit": 7, "seconds": 10},
    {"name": "D192: Ctrl-Break while a child on this console is raw, then its mode back (the parent listens)",
     "args": ["ctrl", "raw", "token"],
     "steps": [{"wait": "child raw\n"}, {"event": "CTRL_BREAK_EVENT"}],
     "out": f"child raw\nexited {STATUS_CONTROL_C_EXIT - (1 << 32)} restored true\n", "exit": 0, "seconds": 30},
    {"name": "D192 with a listener in the raw child first",
     "args": ["ctrl", "listen", "token"],
     "steps": [{"wait": "child listening\n"}, {"event": "CTRL_BREAK_EVENT"}, {"wait": "child raw\n"},
               {"event": "CTRL_BREAK_EVENT"}],
     "out": f"child listening\nchild caught interrupt\nchild raw\nexited {STATUS_CONTROL_C_EXIT - (1 << 32)} "
            "restored true\n", "exit": 0, "seconds": 30},
    {"name": "D187 on Windows' console: every end of raw mode puts the mode back",
     "args": ["ends"], "steps": [],
     "out": "return 0 restored true\nexit 3 restored true\npanic 1 restored true\nindex 1 restored true\n"
            "key 1 restored true\ndeep 1 restored true\nnested 1 restored true\nfails 1 restored true\n"
            "left 0 restored false\n", "exit": 0, "seconds": 60},
    {"name": "MYLA-734: a cooked read's CR LF is \"\\n\", however the reads cut the line",
     "args": ["pieces"],
     "steps": [{"wait": "ready 1\n"}, {"keys": ["h", "e", "l", "l", "o", "Enter"]},
               {"wait": "ready 3\n"}, {"keys": ["h", "e", "l", "l", "o", "Enter"]},
               {"wait": "ready 64\n"}, {"keys": ["h", "e", "l", "l", "o", "Enter"]}],
     "out": "ready 1\n1: [h][e][l][l][o][\\n]\nready 3\n3: [hel][lo][\\n]\nready 64\n64: [hello\\n]\n",
     "exit": 0, "seconds": 30},
]


if __name__ == "__main__":
    unittest.main()
