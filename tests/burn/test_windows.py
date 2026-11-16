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

Skipped where clang, llvm-dlltool, lld-link or Wine is missing (CI installs
them, and MYLA_REQUIRE_TARGETS makes a missing one fail there).
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
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
from std.process import command, args, ExitStatus

// MYLA-706: many sockets at once on the I/O completion port, beside
// children: `clients` connections echoed through loopback, each its own
// pair of tasks, while `kids` children echo their input and an HTTP server
// in this program answers its own client.

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
        Err(e) => { return 0 }
    }
    var msg: [uint8] = []
    for i in 0..size {
        msg.push(97u8 + ((i + k) % 26) as uint8)
    }
    for r in 0..rounds {
        match await s.write_async(msg) {
            Ok(_) => {}
            Err(e) => { return 0 }
        }
        var got: [uint8] = []
        while got.len() < size {
            match await s.read_async(size - got.len()) {
                Ok(b) => {
                    if b.len() == 0 {
                        return 0
                    }
                    for x in b {
                        got.push(x)
                    }
                }
                Err(e) => { return 0 }
            }
        }
        if got != msg {
            return 0
        }
    }
    let c = s.close()
    return 1
}

// A child echoing its input (the helper's `cat`): 1 when it gave it back.
async fun kid(k: int) -> int {
    let want = f"child {k}\n"
    return match await command("./helper.exe").arg("cat").stdin(want).output_async() {
        Ok(o) => if bytes.to_str(o.stdout) == want && o.status == ExitStatus.Exited(0) { 1 } else { 0 }
        Err(e) => 0
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
                }
            }
            Err(e) => {}
        }
    }
    c.close()
    return right
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
    async let served = serve(l, clients)
    async let answered = http.serve_n(hl, 20, handle)
    var fs: [async () -> int] = []
    for k in 0..clients {
        // small messages, and every tenth one past what a socket buffers
        var size = 100 + k
        if k % 10 == 0 {
            size = 300000
        }
        fs.push(async () => await client(port, k, 3, size))
    }
    for k in 0..kids {
        fs.push(async () => await kid(k))
    }
    fs.push(async () => await ask(hport, 20))
    var ok = 0
    for x in await task.all(fs) {
        ok += x
    }
    let echoed = await served
    let http_served = match await answered {
        Ok(n) => n
        Err(e) => -1
    }
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


if __name__ == "__main__":
    unittest.main()
