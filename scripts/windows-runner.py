#!/usr/bin/env python3
"""windows-runner.py: Windows programs built on Linux, run on Windows (MYLA-708,
D213, D214).

  windows-runner.py build OUT [--myla PATH] [--jobs N]
      On Linux: builds for x86_64-windows the examples, the concurrency
      stress programs, tests/burn/test_windows.py's programs (its HELPER and
      process and socket cases, FramesOnWindows' 64 KiB frame, console cases of its
      own), a read of the standard input with a time limit, and myla.exe and
      myla-lsp.exe, into OUT, and writes OUT/cases.json: each case's
      commands and what each must print and exit with (the examples' from
      the interpreter here, as bootstrap-arm64 takes them).

  windows-runner.py run OUT [--wine [CMD]] [--runs N] [--only TEXT] [--list]
      On Windows (CI's windows-latest job): runs every case of OUT and
      reports each; exit status 1 when one failed. With --wine, on Linux,
      Wine stands in for Windows (CMD, default /usr/lib/wine/wine64 or
      wine64 or wine on PATH): what Wine can't show is skipped with its
      reason (a case's `windows_only`), and so is what needs tools that
      aren't there (`myla.exe build` needs clang, lld-link and llvm-dlltool
      for Windows on PATH, or in C:\\Program Files\\LLVM\\bin).

The run needs Python's standard library only and nothing of the checkout
but OUT: a case's programs are under OUT/bin and OUT/tools, the files it
starts with under OUT/files, and it runs in a directory of its own under
OUT/work.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
FORMAT = 1
STRESS_WORKERS = ["1", "4", "16"]
LLVM_TOOLS = ["clang", "lld-link", "llvm-dlltool"]

# --- the console cases ---------------------------------------------------------
# Each: (name, source, steps), a step a dict of `Step`'s fields (see `step`).
# They are test_windows.HelloWorld's and Workers' programs (MYLA-702,
# MYLA-703), what a console program does: its output in UTF-8 as is, its
# exit code, a runtime error, its command line and environment, the heap,
# the standard input, files, Windows' paths, tasks, a stack overflow on the
# main thread and a worker's.

PATHS = r'''import std.path as path
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
    print(path.anchor(cwd))
    print(fs.is_file(path.join(cwd, "main.my")))
    print(glob.matches("*/*.my", "src\\main.my"))
    match fs.make_dir_all(cwd + "\\deep\\er") {
        Ok(()) => print(fs.is_dir("deep/er"))
        Err(e) => print(f"{e}")
    }
}
'''

FILES = r'''import std.fs as fs
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

ARGS = ('from std.process import args, env\n'
        'fun main() {\n'
        '    let a = args()\n'
        '    print(a[0].ends_with(".exe"))\n'
        '    var i = 1\n'
        '    while i < a.len() {\n'
        '        print(f"[{a[i]}]")\n'
        '        i += 1\n'
        '    }\n'
        '    print(env("MYLA_WIN_TEST").unwrap_or("none"))\n'
        '    print(env("MYLA_WIN_NONE").unwrap_or("none"))\n'
        '}\n')

HEAP = ('fun main() {\n'
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

LINES = ('from std.io import stdin\n'
         'fun main() {\n'
         '    var r = stdin()\n'
         '    while true {\n'
         '        match r.read_line() {\n'
         '            Ok(Some(l)) => { print(f"<{l}>") },\n'
         '            _ => { break },\n'
         '        }\n'
         '    }\n'
         '}\n')

TASKS = ('import std.task as task\n'
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

# The standard input read with a time limit (`Reader.ready(ms)`, std.platform's
# `poll_read`, which asks the pipe how much it holds, `PeekNamedPipe`): none
# within 300 ms while the pipe is open and empty, at once once a line came,
# and at once at its end. It says each and waits for its parent between them.
READY = '''from std.io import stdin
import std.time as time

fun main() {
    var r = stdin()
    let t0 = time.now()
    let empty = r.ready(300)
    let waited = t0.elapsed().as_millis()
    print(f"empty {empty} waited {waited >= 250 && waited < 5000}")
    let t1 = time.now()
    let some = r.ready(20000)
    print(f"input {some} at once {t1.elapsed().as_millis() < 15000}")
    match r.read_line() {
        Ok(Some(l)) => { print(f"read {l}") },
        _ => { print("no line") },
    }
    let t2 = time.now()
    let end = r.ready(20000)
    print(f"end {end} at once {t2.elapsed().as_millis() < 15000}")
    match r.read_line() {
        Ok(None) => { print("eof") },
        _ => { print("more") },
    }
}
'''

READY_DIALOG = [
    {"expect": "empty false waited true"},
    {"send": "go\n"},
    {"expect": "input true at once true"},
    {"expect": "read go"},
    {"close": True},
]
READY_OUT = "end true at once true\neof\n"

# READY as the child of a Windows program, whose input is a pipe of
# `CreatePipe`'s: what Wine can show too, where a Linux parent's pipe is no
# named pipe to Windows (MYLA-702).
READY_PARENT = '''from std.process import command, ExitStatus
from std.ioerror import IoError
from std.io import buffered
import std.bytes as bytes

fun line(r: Result<Option<str>, IoError>) -> str {
    return match r {
        Ok(Some(l)) => l
        Ok(None) => "<end>"
        Err(e) => f"error {e}"
    }
}

fun main() {
    match command("./ready.exe").spawn() {
        Ok(c) => {
            var child = c
            var w = match child.take_stdin() { Some(s) => s, None => panic("no input") }
            var lines = buffered(match child.take_stdout() { Some(s) => s, None => panic("no output") })
            print(line(lines.read_line()))
            let a = w.write(bytes.from_str("go\\n"))
            print(line(lines.read_line()))
            print(line(lines.read_line()))
            let closed = w.close()
            print(line(lines.read_line()))
            print(line(lines.read_line()))
            print(line(lines.read_line()))
            print(match child.wait() {
                Ok(ExitStatus.Exited(n)) => f"exit {n}"
                Ok(ExitStatus.Signaled(s)) => f"signal {s}"
                Err(e) => f"error {e}"
            })
        }
        Err(e) => { print(f"error {e}") },
    }
}
'''

# what `myla.exe test` runs (and `myla test` here gives)
TEST_FILE = ('#test(2)[4]\n#test(3)[10]\nfun square(x: int) -> int {\n    return x * x\n}\n\n'
             '#test\nfun sums() {\n    assert(square(3) + square(4) == 25, "five squared")\n}\n')
TYPE_ERROR = 'fun main() {\n    let x: int = "s"\n    print(x)\n}\n'
HELLO = 'fun main() {\n    print("Hello from Myla on Windows")\n}\n'


def lsp_input() -> str:
    def frame(body: str) -> str:
        return f"Content-Length: {len(body)}\r\n\r\n{body}"
    return (frame('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"capabilities":{}}}')
            + frame('{"jsonrpc":"2.0","id":2,"method":"shutdown"}')
            + frame('{"jsonrpc":"2.0","method":"exit"}'))


def step(argv, stdout=None, stderr="", code=0, stdin="", env=None, timeout=120, has=(), subst=False,
         path_dir=False, expect_timeout=False, dialog=None, repeat=False, needs=(), new_console=False):
    """A command of a case and what it must do. `argv[0]` is a program under
    OUT (`bin/…`, `tools/…`) or in the case's directory (`./…`). `stdout`
    exactly (None: not checked) or containing each of `has`; `stderr`
    exactly (None: not checked); `subst`: @CWD@ and @ANCHOR@ in `stdout`
    and `env` are the case's directory as Windows names it and its drive;
    `path_dir`: that directory first on the program search path; `dialog`:
    lines expected and text sent before the rest is read; `expect_timeout`:
    it must still run after `timeout` seconds (then killed); `repeat`: it
    runs --runs times; `needs`: tools it needs on PATH; `new_console`: it
    gets a console of its own (CREATE_NEW_CONSOLE), its standard streams
    still this script's pipes (skipped under Wine)."""
    return {"argv": list(argv), "stdout": stdout, "stderr": stderr, "code": code, "stdin": stdin,
            "env": dict(env or {}), "timeout": timeout, "has": list(has), "subst": subst, "path_dir": path_dir,
            "expect_timeout": expect_timeout, "dialog": dialog, "repeat": repeat, "needs": list(needs),
            "new_console": new_console}


# MYLA-707 (std.term and std.signal on the console API) adds its console
# cases here: (name, source, steps), as `console_cases` makes them, the
# program built as `bin/console-<name>.exe` from a `main.my`; or (name,
# source, steps, why) for one that Wine can't show (a real console's raw
# input, its window's size), skipped there with `why`. A step with
# `new_console=True` runs in a console of its own.
MORE_CONSOLE_CASES: list[tuple] = []


def console_cases(deep: str, busy_entry: str) -> list[tuple[str, str, list[dict]]]:
    exe = lambda name: f"bin/console-{name}.exe"
    out = "\u00e9\u4e2d"
    return [
        ("hello", 'fun main() {\n    print("hello, world")\n}\n', [step([exe("hello")], "hello, world\n")]),
        # D215: the same bytes as on Linux, no CRLF
        ("utf8", ('from std.io import eprintln\nfun main() {\n    print("h\\u{e9}llo, w\\u{f6}rld \\u{2713} \\u{1f600}")\n'
                  '    eprintln("to stderr")\n    print("a\\r\\nb\\n")\n}\n'),
         [step([exe("utf8")], "h\u00e9llo, w\u00f6rld \u2713 \U0001f600\na\r\nb\n\n", "to stderr\n")]),
        ("exit", 'from std.process import exit\nfun main() {\n    print("bye")\n    exit(7)\n}\n',
         [step([exe("exit")], "bye\n", code=7)]),
        ("runtime-error", 'fun main() {\n    let xs = [1, 2, 3]\n    var i = 2\n    i += 5\n    print(xs[i])\n}\n',
         [step([exe("runtime-error")], "", "runtime error: list index 7 out of bounds (len 3)\n  --> main.my:5:13\n",
               code=1)]),
        # the command line split as Windows' C runtime splits it, in UTF-8
        ("args", ARGS, [step([exe("args"), "plain", "two words", 'quo"te', "back\\slash", "tail\\", "", out],
                             f'true\n[plain]\n[two words]\n[quo"te]\n[back\\slash]\n[tail\\]\n[]\n[{out}]\nv\u00e4lue=1\nnone\n',
                             env={"MYLA_WIN_TEST": "v\u00e4lue=1"})]),
        ("heap", HEAP, [step([exe("heap")], "300000 300 299000 899997\n")]),
        ("stdin-lines", LINES, [step([exe("stdin-lines")], "<one>\n<tw\u00f6>\n", stdin="one\ntw\u00f6\n")]),
        ("files", FILES, [step([exe("files")], "ok\nok\nh\u00e9llo!\nsub,\u4e2d.txt\n7 true 666 true\ntrue\nIsADirectory\n"
                               "IsADirectory\nNotEmpty\nNotADirectory\nAlreadyExists\nok\nNotFound\nok\nfalse\n")]),
        ("paths", PATHS, [step([exe("paths")], "a\\b\nC:\\y\nC:\\a\nnone\nC:/b/c\ntrue\n../d\n@CWD@\n@ANCHOR@\ntrue\ntrue\ntrue\n",
                               subst=True)]),
        ("tasks", TASKS, [step([exe("tasks")], "30\n45\ntrue\n")]),
        ("stack-overflow", deep + "fun main() {\n    print(deep(1))\n}\n",
         [step([exe("stack-overflow")], "", "runtime error: stack overflow\n", code=1)]),
        # the child overflows on the second worker, the entry's busy
        ("worker-stack-overflow", deep + "async fun child() -> int {\n    return deep(1)\n}\n\n" + busy_entry,
         [step([exe("worker-stack-overflow")], "", "runtime error: stack overflow\n", code=1, env={"MYLA_THREADS": "2"},
               timeout=60)]),
        # two workers: the child runs beside the busy entry and ends the
        # program (D97); one: it never runs
        ("workers", 'from std.process import exit\n\nasync fun child() -> int {\n    print("child")\n'
                    '    exit(3)\n    return 0\n}\n\n' + busy_entry,
         [step([exe("workers")], "child\n", code=3, env={"MYLA_THREADS": "2"}, timeout=60),
          step([exe("workers")], None, None, env={"MYLA_THREADS": "1"}, timeout=3, expect_timeout=True)]),
    ] + MORE_CONSOLE_CASES


# --- building (Linux) ------------------------------------------------------------

def default_myla() -> str:
    built = os.path.join(_REPO, "build", "myla")
    if os.access(built, os.X_OK):
        return built
    sys.path.insert(0, _REPO)
    from tests.burn._tools import selfhost_tool
    return selfhost_tool("main")


def build(out: str, myla: str, jobs: int) -> int:
    sys.path.insert(0, _REPO)
    from tests.burn import test_windows as tw
    from tests.burn.test_concurrency_stress import _DIR as STRESS_DIR, EXPECTED, EXPECTED_STDERR

    stdlib = os.path.join(_REPO, "lib")
    myla = os.path.abspath(myla)
    if os.path.exists(out):
        shutil.rmtree(out)
    for sub in ("bin", "tools", "files"):
        os.makedirs(os.path.join(out, sub))
    out = os.path.abspath(out)
    scratch = tempfile.mkdtemp(prefix="windows-runner-")
    start = time.monotonic()
    builds: list[tuple[str, str, str]] = []   # (exe under OUT, source file, directory it is built in)
    cases: list[dict] = []

    def program(exe: str, source: str, name: str = "main.my") -> None:
        """`source` built as OUT/`exe` from a file `name` of a directory of
        its own (a runtime error's position names it)."""
        d = os.path.join(scratch, exe.replace("/", "_"))
        os.makedirs(d)
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(source)
        builds.append((exe, name, d))

    def file(name: str, text: str) -> str:
        """`text` kept as OUT/files/`name`; its path under OUT."""
        path = os.path.join(out, "files", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return "files/" + name

    def case(name: str, steps: list[dict], files: dict | None = None, windows_only: str = "") -> None:
        cases.append({"name": name, "steps": steps, "files": files or {}, "windows_only": windows_only})

    def linux(argv: list[str], cwd: str, stdin: str = "") -> dict:
        r = subprocess.run(argv, cwd=cwd, input=stdin.encode(), capture_output=True, timeout=600)
        return {"stdout": r.stdout.decode("utf-8", "backslashreplace"),
                "stderr": r.stderr.decode("utf-8", "backslashreplace"), "code": r.returncode}

    # the console: test_windows' HelloWorld and Workers programs, and MYLA-707's
    for name, source, steps, *why in console_cases(tw.DEEP, tw.BUSY_ENTRY):
        program(f"bin/console-{name}.exe", source)
        files = {"main.my": file(f"console-{name}/main.my", source)} if name == "paths" else {}
        case(f"console/{name}", steps, files, windows_only=why[0] if why else "")

    # the standard input with a time limit: from this script's pipe, which is
    # a named pipe on Windows, and from a Windows program's
    program("bin/ready.exe", READY)
    program("bin/ready-parent.exe", READY_PARENT)
    case("stdin/ready", [step(["bin/ready.exe"], READY_OUT, dialog=READY_DIALOG, timeout=60)],
         windows_only="Wine hands a Linux parent's pipe over as no named pipe: PeekNamedPipe fails there and the "
                      "input is taken for ready (MYLA-702); stdin/ready-from-a-child is its ground here")
    case("stdin/ready-from-a-child",
         [step(["./ready-parent.exe"], "empty false waited true\ninput true at once true\nread go\n"
               "end true at once true\neof\n<end>\nexit 0\n", timeout=60)],
         {"ready-parent.exe": "bin/ready-parent.exe", "ready.exe": "bin/ready.exe"})

    # MYLA-717: the 64 KiB frame on the main thread and a worker
    program("bin/frames.exe", tw.FRAMES)
    frames_out = tw.FRAMES_OUT.decode()
    case("frames/64-kib", [step(["bin/frames.exe"], frames_out, env={"MYLA_THREADS": "2"}, repeat=True),
                           step(["bin/frames.exe"], frames_out, env={"MYLA_THREADS": "1"}),
                           step(["bin/frames.exe"], frames_out, env={"MYLA_THREADS": "16"})])

    # processes (MYLA-705): std.process with test_windows' HELPER as the
    # child, and many children on many workers
    program("bin/helper.exe", tw.HELPER)
    program("bin/children.exe", tw.CHILDREN)
    program("bin/many-children.exe", tw.MANY_CHILDREN)
    helper = {"helper.exe": "bin/helper.exe"}
    case("process/std-process",
         [step(["./prog.exe"], tw.CHILDREN_OUT, env={"MYLA_B": "kept"}, path_dir=True, timeout=300)],
         dict(helper, **{"prog.exe": "bin/children.exe",
                         "echo-args.bat": file("echo-args.bat", "@echo [%1] [%2] [%3] [%4]\r\n")}))
    case("process/many-children",
         [step(["./prog.exe"], "400\n", None, env={"MYLA_THREADS": w}, timeout=300) for w in ("4", "16")],
         dict(helper, **{"prog.exe": "bin/many-children.exe"}))

    # sockets and the poller on an I/O completion port (MYLA-706): a TCP
    # echo through loopback (test_net's), an HTTP server and its client in
    # one program (test_http's), test_windows.Sockets' many connections
    # beside children and its close that waits for its send; MYLA-726: a
    # child's input written while its output is read, on one worker too
    from tests.burn import test_http as th, test_net as tn
    program("bin/net-echo.exe", tn.ECHO)
    program("bin/http-one-program.exe", th.ONE_PROGRAM)
    program("bin/sockets.exe", tw.SOCKETS)
    program("bin/closed-while-sending.exe", tw.CLOSED_WHILE_SENDING)
    program("bin/input-while-output.exe", tw.INPUT_WHILE_OUTPUT)
    case("net/echo", [step(["bin/net-echo.exe"], tn.ECHO_OUT, env={"MYLA_THREADS": w}) for w in ("1", "4")])
    case("net/http-one-program", [step(["bin/http-one-program.exe"], th.ONE_PROGRAM_OUT, env={"MYLA_THREADS": w})
                                  for w in ("1", "4")])
    case("net/sockets-and-children",
         [step(["./prog.exe", "200", "50"], "250 of 250 right, http 20, echoed true\n", env={"MYLA_THREADS": w},
               timeout=300) for w in STRESS_WORKERS],
         dict(helper, **{"prog.exe": "bin/sockets.exe"}))
    case("net/a-close-waits-for-its-send",
         [step(["bin/closed-while-sending.exe"], "4000000 4000000\n" * 3, env={"MYLA_THREADS": w}) for w in ("1", "4")])
    case("process/input-while-output",
         [step(["./prog.exe"], "600000 600000 0\n", env={"MYLA_THREADS": w}, timeout=60) for w in ("1", "2", "4")],
         dict(helper, **{"prog.exe": "bin/input-while-output.exe"}))

    # the examples, against what the interpreter gives here
    examples = sorted(f for f in os.listdir(os.path.join(_REPO, "examples")) if f.endswith(".my"))
    examples = [f"examples/{f}" for f in examples] + ["examples/stdio/main.my", "examples/modules/main.my"]
    for rel in examples:
        stem = rel[len("examples/"):-len(".my")].replace("/", "-")
        builds.append((f"bin/example-{stem}.exe", rel, _REPO))
        want = linux([myla, "run", rel, "--stdlib", stdlib], _REPO)
        case(f"examples/{stem}", [step([f"bin/example-{stem}.exe"], want["stdout"], want["stderr"], want["code"])])
        # the same through myla.exe's interpreter, the file where it was (an
        # example of a directory of its own with the directory's modules)
        paths = [rel]
        if rel.count("/") > 1:
            tree = os.path.join(_REPO, os.path.dirname(rel))
            paths = sorted(os.path.relpath(os.path.join(root, n), _REPO).replace(os.sep, "/")
                           for root, _, names in os.walk(tree) for n in names if n.endswith(".my"))
        files = {}
        for p in paths:
            with open(os.path.join(_REPO, p), encoding="utf-8") as fh:
                files[p] = file(p, fh.read())
        case(f"interpreter/{stem}", [step(["tools/myla.exe", "run", rel], want["stdout"], want["stderr"], want["code"])],
             files)

    # the concurrency stress programs on 1, 4 and 16 workers (t27's children
    # are Linux's `echo`: process/many-children is its ground here)
    for name, (want_out, want_code) in sorted(EXPECTED.items()):
        if name == "t27_children_read_as_they_write":
            continue
        builds.append((f"bin/{name}.exe", os.path.join(STRESS_DIR, name + ".my"), _REPO))
        case(f"stress/{name}", [step([f"bin/{name}.exe"], want_out, EXPECTED_STDERR.get(name), want_code,
                                     env={"MYLA_THREADS": w}, repeat=True) for w in STRESS_WORKERS])

    # the tools: myla.exe and myla-lsp.exe (the language server)
    builds.append(("tools/myla.exe", "selfhost/main.my", _REPO))
    builds.append(("tools/myla-lsp.exe", "tools/lsp/main.my", _REPO))
    tdir = os.path.join(scratch, "tool-cases")
    os.makedirs(tdir)
    tool_files = {}
    for name, text in (("t.my", TEST_FILE), ("bad.my", TYPE_ERROR), ("hello.my", HELLO)):
        with open(os.path.join(tdir, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        tool_files[name] = file("tools/" + name, text)
    tested = linux([myla, "test", "t.my", "--stdlib", stdlib], tdir)
    checked = linux([myla, "check", "bad.my", "--stdlib", stdlib], tdir)
    native = linux([myla, "test", "t.my", "--native", "--stdlib", stdlib], tdir)
    case("tools/myla-run", [step(["tools/myla.exe", "run", "hello.my"], "Hello from Myla on Windows\n")], tool_files)
    case("tools/myla-check", [step(["tools/myla.exe", "check", "bad.my"], checked["stdout"], checked["stderr"],
                                   checked["code"])], tool_files)
    case("tools/myla-test", [step(["tools/myla.exe", "test", "t.my"], tested["stdout"], tested["stderr"],
                                  tested["code"])], tool_files)
    case("tools/myla-lsp", [step(["tools/myla-lsp.exe"], None, None, stdin=lsp_input(),
                                 has=['"id":1,"result":{', '"id":2,"result":null'])])
    # building on Windows itself, with the LLVM there (D211)
    case("tools/myla-build", [
        step(["tools/myla.exe", "build", "hello.my", "-o", "hello.exe"], "", "", needs=LLVM_TOOLS, timeout=300),
        step(["./hello.exe"], "Hello from Myla on Windows\n", needs=LLVM_TOOLS),
        step(["tools/myla.exe", "build", "hello.my"], "", "", needs=LLVM_TOOLS, timeout=300),
        step(["./a.exe"], "Hello from Myla on Windows\n", needs=LLVM_TOOLS),
        # a harness of the file's cases, its cases its children (MYLA-705)
        step(["tools/myla.exe", "test", "t.my", "--native"], native["stdout"], native["stderr"], native["code"],
             env={"TMPDIR": "@CWD@"}, subst=True, needs=LLVM_TOOLS, timeout=300),
    ], tool_files)

    def make(b: tuple[str, str, str]) -> str:
        exe, src, cwd = b
        r = subprocess.run([myla, "build", src, "--target", "x86_64-windows", "--stdlib", stdlib,
                            "-o", os.path.join(out, exe)], cwd=cwd, capture_output=True, text=True, timeout=900)
        return "" if r.returncode == 0 else f"{exe} ({src}): {r.stderr.strip() or r.returncode}"

    with ThreadPoolExecutor(jobs) as pool:
        failed = [f for f in pool.map(make, builds) if f]
    shutil.rmtree(scratch, ignore_errors=True)
    for f in failed:
        print(f"build failed: {f}")
    with open(os.path.join(out, "cases.json"), "w", encoding="utf-8") as fh:
        json.dump({"format": FORMAT, "cases": cases}, fh, indent=1, ensure_ascii=False)
    print(f"{len(builds) - len(failed)} of {len(builds)} programs built for x86_64-windows, {len(cases)} cases, "
          f"in {time.monotonic() - start:.0f} s: {out}")
    return 1 if failed else 0


# --- running (Windows, or Linux under Wine) --------------------------------------

class Runner:
    def __init__(self, bundle: str, wine: list[str], runs: int):
        self.bundle = os.path.abspath(bundle)
        self.wine = wine
        self.runs = runs
        self.env = dict(os.environ)
        self.tools_missing = self.find_tools()

    def find_tools(self) -> list[str]:
        """The LLVM tools `myla.exe build` needs that the machine hasn't (all
        of them under Wine: Linux's aren't Windows programs). LLVM's
        installer's directory goes on PATH when they are there."""
        if self.wine:
            return list(LLVM_TOOLS)
        llvm = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "LLVM", "bin")
        path = self.env.get("PATH", "")
        if not all(shutil.which(t, path=path) for t in LLVM_TOOLS) and os.path.isdir(llvm):
            self.env["PATH"] = llvm + os.pathsep + path
        missing = []
        for t in LLVM_TOOLS:
            found = shutil.which(t, path=self.env["PATH"])
            if not found:
                missing.append(t)
                continue
            r = subprocess.run([found, "--version"], capture_output=True, text=True)
            version = r.stdout.strip().split("\n")[0] if r.returncode == 0 else ""
            print(f"tool {t}: {found}" + (f" ({version})" if version else ""))
        for t in missing:
            print(f"tool {t}: not found")
        return missing

    def windows_path(self, path: str) -> str:
        """`path` as the Windows program names it (Wine's drive Z: is /)."""
        if self.wine:
            return "Z:" + os.path.realpath(path).replace("/", "\\")
        return os.path.abspath(path)

    def program(self, word: str, work: str) -> str:
        if word.startswith("./"):
            return os.path.join(work, word[2:])
        return os.path.join(self.bundle, *word.split("/"))

    def run_case(self, c: dict) -> tuple[str, str]:
        """("ok" | "FAIL" | "skip", what)"""
        if c["windows_only"] and self.wine:
            return "skip", "under Wine: " + c["windows_only"]
        if self.wine and any(s.get("new_console") for s in c["steps"]):
            return "skip", "under Wine: a console of its own for a program a Linux process starts"
        needs = sorted({t for s in c["steps"] for t in s["needs"] if t in self.tools_missing})
        if needs:
            return "skip", f"needs {', '.join(needs)}, not on this machine's PATH (nor in LLVM's directory)"
        work = os.path.join(self.bundle, "work", c["name"].replace("/", "-"))
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        for dest, src in c["files"].items():
            target = os.path.join(work, *dest.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(os.path.join(self.bundle, *src.split("/")), target)
        cwd = self.windows_path(work)
        subst = {"@CWD@": cwd, "@ANCHOR@": cwd[:3]}
        for k, s in enumerate(c["steps"]):
            for n in range(self.runs if s["repeat"] else 1):
                bad = self.run_step(s, work, subst)
                if bad:
                    run = f", run {n + 1}" if s["repeat"] and self.runs > 1 else ""
                    return "FAIL", f"step {k + 1}{run} ({' '.join(s['argv'])}): {bad}"
        shutil.rmtree(work, ignore_errors=True)
        return "ok", ""

    def run_step(self, s: dict, work: str, subst: dict) -> str:
        """What step `s` did wrong, "" for nothing."""
        def put(text: str) -> str:
            if s["subst"]:
                for k, v in subst.items():
                    text = text.replace(k, v)
            return text
        env = dict(self.env)
        for k, v in s["env"].items():
            env[k] = put(v)
        if s["path_dir"]:
            if self.wine:
                env["WINEPATH"] = subst["@CWD@"]
            else:
                env["PATH"] = work + os.pathsep + env.get("PATH", "")
        argv = [*self.wine, self.program(s["argv"][0], work), *s["argv"][1:]]
        flags = subprocess.CREATE_NEW_CONSOLE if s.get("new_console") and sys.platform == "win32" else 0
        # a dialog reads its output unbuffered: a line at a time, nothing
        # of the rest taken from what `communicate` reads after it
        proc = subprocess.Popen(argv, cwd=work, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, creationflags=flags, bufsize=0 if s["dialog"] else -1)
        deadline = time.monotonic() + s["timeout"]
        got_lines = []
        if s["dialog"]:
            for turn in s["dialog"]:
                if "send" in turn:
                    proc.stdin.write(turn["send"].encode())
                    proc.stdin.flush()
                elif "close" in turn:
                    proc.stdin.close()
                else:
                    line = read_line(proc.stdout, deadline - time.monotonic())
                    if line is None:
                        stop(proc)
                        return f"no line {turn['expect']!r} within {s['timeout']} s (after {got_lines!r})"
                    text = line.decode("utf-8", "backslashreplace").rstrip("\r\n")
                    got_lines.append(text)
                    if text != turn["expect"]:
                        stop(proc)
                        return f"said {text!r}, expected {turn['expect']!r}"
        stdin = None if s["dialog"] else s["stdin"].encode()
        try:
            out, err = proc.communicate(stdin, timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            out, err = stop(proc)
            if s["expect_timeout"]:
                return ""
            return f"still running after {s['timeout']} s; stdout {clip(out)}, stderr {clip(err)}"
        if s["expect_timeout"]:
            return f"ended (exit {proc.returncode}) within {s['timeout']} s, expected it to run on"
        stdout = out.decode("utf-8", "backslashreplace")
        stderr = err.decode("utf-8", "backslashreplace")
        problems = []
        if proc.returncode != s["code"]:
            problems.append(f"exit {proc.returncode}, expected {s['code']}")
        if s["stdout"] is not None and stdout != put(s["stdout"]):
            problems.append("stdout " + differs(stdout, put(s["stdout"])))
        for h in s["has"]:
            if h not in stdout:
                problems.append(f"stdout {clip(out)} without {h!r}")
        if s["stderr"] is not None and stderr != s["stderr"]:
            problems.append("stderr " + differs(stderr, s["stderr"]))
        return "; ".join(problems)


def stop(proc: subprocess.Popen) -> tuple[bytes, bytes]:
    """`proc` killed, and what it wrote (nothing if a child of its holds its
    streams open 30 s on)."""
    proc.kill()
    try:
        return proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        return b"", b""


def read_line(stream, timeout: float) -> bytes | None:
    """A line of `stream` within `timeout` seconds, None for none."""
    got: list[bytes] = []
    t = threading.Thread(target=lambda: got.append(stream.readline()), daemon=True)
    t.start()
    t.join(max(0.0, timeout))
    return got[0] if got and got[0] else None


def clip(b: bytes, n: int = 300) -> str:
    return repr(b[:n]) + ("…" if len(b) > n else "")


def differs(got: str, want: str) -> str:
    at = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
    lo = max(0, at - 60)
    return (f"differs at {at} of {len(got)} (expected {len(want)}): got {got[lo:at + 120]!r}, "
            f"expected {want[lo:at + 120]!r}")


def wine_command(given: str) -> list[str]:
    if given:
        return given.split()
    for name in ("wine64", "wine"):
        found = shutil.which(name)
        if found:
            return [found]
    if os.access("/usr/lib/wine/wine64", os.X_OK):
        return ["/usr/lib/wine/wine64"]
    sys.exit("windows-runner: no Wine found (give --wine CMD)")


def prepare_wine(wine: list[str]) -> None:
    """Wine's defaults, its server kept a minute past its last program, and
    its services started with their streams on /dev/null, so they don't
    hold a case's pipes (as tests/burn/_native.py's `wine_env`)."""
    os.environ.setdefault("WINEDEBUG", "-all")
    os.environ.setdefault("WINEPREFIX", os.path.join(_REPO, "build", "wineprefix"))
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    server = shutil.which("wineserver") or os.path.join(os.path.dirname(wine[0]), "wineserver")
    if os.access(server, os.X_OK):
        subprocess.run([server, "-p60"], **quiet)
    boot = ["wineboot"] if os.path.isdir(os.environ["WINEPREFIX"]) else ["wineboot", "--init"]
    subprocess.run([*wine, *boot], timeout=300, **quiet)


def run(bundle: str, wine: list[str], runs: int, only: list[str], listing: bool) -> int:
    with open(os.path.join(bundle, "cases.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("format") != FORMAT:
        sys.exit(f"windows-runner: {bundle}/cases.json is of format {data.get('format')}, this script reads {FORMAT}")
    cases = [c for c in data["cases"] if not only or any(o in c["name"] for o in only)]
    if listing:
        for c in cases:
            print(c["name"])
        return 0
    if wine:
        prepare_wine(wine)
    runner = Runner(bundle, wine, runs)
    tally = {"ok": 0, "FAIL": 0, "skip": 0}
    lines = []
    start = time.monotonic()
    for c in cases:
        t0 = time.monotonic()
        verdict, what = runner.run_case(c)
        tally[verdict] += 1
        line = f"{verdict:4} {c['name']} ({time.monotonic() - t0:.1f} s)" + (f": {what}" if what else "")
        lines.append(line)
        print(line, flush=True)
        if verdict == "skip" and not wine and os.environ.get("GITHUB_ACTIONS"):
            # on the runner a skip is news: an annotation on the run's page
            print(f"::warning title=Windows runner::{c['name']} skipped: {what}", flush=True)
    where = f"under Wine ({' '.join(wine)})" if wine else "on Windows"
    summary = (f"{tally['ok']} passed, {tally['FAIL']} failed, {tally['skip']} skipped of {len(cases)} cases {where}, "
               f"in {time.monotonic() - start:.0f} s")
    print(summary)
    report = os.environ.get("GITHUB_STEP_SUMMARY")
    if report:
        with open(report, "a", encoding="utf-8") as fh:
            fh.write(f"### Windows runner\n\n{summary}\n\n")
            for line in lines:
                if not line.startswith("ok"):
                    fh.write(f"- `{line}`\n")
    return 1 if tally["FAIL"] else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the programs and their cases (Linux)")
    b.add_argument("out")
    b.add_argument("--myla", default="", help="the myla that builds them (default build/myla, else the tests' own)")
    b.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    r = sub.add_parser("run", help="run the cases (Windows, or Linux with --wine)")
    r.add_argument("out")
    r.add_argument("--wine", nargs="?", const="", default=None, help="Wine as Windows' stand-in (its command)")
    r.add_argument("--runs", type=int, default=1, help="runs of each repeated step (the stress programs, …)")
    r.add_argument("--only", action="append", default=[], help="cases whose name has this text (repeatable)")
    r.add_argument("--list", action="store_true", help="name the cases without running them")
    args = ap.parse_args()
    # what a program printed, in any script, on a console or pipe of any
    # code page (Windows' Python writes its own in the ANSI one)
    sys.stdout.reconfigure(errors="backslashreplace")
    if args.cmd == "build":
        return build(args.out, args.myla or default_myla(), args.jobs)
    wine = wine_command(args.wine) if args.wine is not None else []
    if not wine and sys.platform != "win32" and not args.list:
        sys.exit("windows-runner: run the cases on Windows, or here with --wine")
    return run(args.out, wine, args.runs, args.only, args.list)


if __name__ == "__main__":
    sys.exit(main())
