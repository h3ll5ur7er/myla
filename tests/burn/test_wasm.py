"""The wasm32-wasi backend (MYLA-158, D125): programs built with `--target
wasm32-wasi` (selfhost/ir_wasm.my, selfhost/runtime_wasm.my and
lib/std/platform_wasm.my), assembled by clang, linked by wasm-ld and run
under Node through tools/wasm/run.mjs (our WASI shim), give what the same
programs built for x86-64 give (stdout, stderr and the exit code). The
x86-64 build is the reference: its own tests hold it to the interpreter.

Skipped where node, clang (with its wasm32 target) or wasm-ld is missing.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, native_compiler
from . import test_time
from .test_aarch64 import LIBRARY_WITHOUT_THE_RUNTIME, PROGRAMS, build_x86, run

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
RUNNER = os.path.join(_REPO, "tools", "wasm", "run.mjs")


def _have_wasm() -> bool:
    if not all(shutil.which(t) for t in ("node", "clang", "wasm-ld")):
        return False
    p = subprocess.run(["clang", "--print-targets"], capture_output=True, text=True)
    return "wasm32" in p.stdout


HAVE_WASM = _have_wasm()
WASM_SKIP = "the wasm tests need node, clang with its wasm32 target and wasm-ld"


@unittest.skipUnless(os.environ.get("MYLA_REQUIRE_TARGETS"), "MYLA_REQUIRE_TARGETS is not set")
class WasmTools(unittest.TestCase):
    """CI sets MYLA_REQUIRE_TARGETS, so a missing tool fails there instead of
    skipping the target's tests unnoticed (MYLA-268)."""

    def test_the_tools_are_there(self):
        self.assertTrue(HAVE_WASM, WASM_SKIP)

# V8's stack for deep recursion (the main thread's is 8 MiB)
NODE = ["node", "--stack-size=7000", RUNNER]


def build_wasm(src: str, out: str, stdlib: str = STDLIB_ROOT) -> None:
    with open(out + ".s", "wb") as fh:
        subprocess.run([native_compiler(), src, stdlib, "--target", "wasm32-wasi"], stdout=fh, check=True, cwd=_REPO)
    subprocess.run(["clang", "--target=wasm32-wasi", "-mtail-call", "-mbulk-memory", "-mnontrapping-fptoint", "-msign-ext",
                    "-c", "-o", out + ".o", out + ".s"], check=True)
    subprocess.run(["wasm-ld", "--stack-first", "-z", "stack-size=8388608", "-o", out, out + ".o"], check=True)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WASM, WASM_SKIP)
class WasmParity(unittest.TestCase):
    def same(self, src: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xb, wb = os.path.join(tmp, "x86"), os.path.join(tmp, "prog.wasm")
            build_x86(src, xb)
            build_wasm(src, wb)
            self.assertEqual(run(NODE + [wb]), run([xb]))

    def test_a_library_without_the_runtime(self):
        # the runtime and the platform module the tools carry, for wasm32
        # (MYLA-268): a library directory without them takes theirs
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "lib", "std"))
            path = os.path.join(tmp, "prog.my")
            with open(path, "w") as fh:
                fh.write(LIBRARY_WITHOUT_THE_RUNTIME)
            exe = os.path.join(tmp, "prog.wasm")
            build_wasm(path, exe, os.path.join(tmp, "lib"))
            self.assertEqual(run(NODE + [exe]), ("b1\n", "", 0))

    def test_a_closure_gets_its_environment_as_a_parameter(self):
        # D130: a function value's environment travels as its last parameter,
        # not through a memory word every call shares (which would stand in
        # the way of threads); lambdas, partial applications, compositions,
        # plain functions and async lambdas as values all agree with x86-64
        source = ("import std.task as task\n\n"
                  "fun twice(f: (int) -> int, x: int) -> int {\n    return f(f(x))\n}\n\n"
                  "fun add(a: int, b: int) -> int {\n    return a + b\n}\n\n"
                  "fun pick(k: int) -> (int) -> int {\n    if k > 0 {\n        return (x: int) => x * k\n    }\n"
                  "    return add(_, k)\n}\n\n"
                  "fun apply(f: (int) -> int, x: int) -> int {\n    become f(x)\n}\n\n"
                  "#main\nasync fun main() {\n    let k = 3\n    let f = (x: int) => x + k\n"
                  "    print(twice(f, 1))\n    print(twice(add(_, 10), 1))\n    print(twice(f >> add(_, 100), 0))\n"
                  "    let g = add\n    print(g(2, 5))\n    print(pick(4)(5) + pick(0)(5))\n"
                  "    print(apply((x: int) => x + k, 4) + apply(add(_, 1), 4))\n"
                  "    let names = [\"a\", \"bb\"]\n    let size = (i: int) => names[i].len()\n    print(size(1))\n"
                  "    let jobs: [async () -> int] = [async () => k * 2, async () => k * 3]\n"
                  "    let rs = await task.all(jobs)\n    print(rs[0] + rs[1])\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "closures.my")
            with open(path, "w") as fh:
                fh.write(source)
            self.same(path)
            asm = subprocess.run([native_compiler(), path, STDLIB_ROOT, "--target", "wasm32-wasi"], capture_output=True,
                                 text=True, check=True, cwd=_REPO).stdout
            self.assertEqual(asm.count("myla_env"), 0)

    def test_one_worker_makes_no_deep_copies(self):
        # D133: with one worker nothing is shared between threads, so values
        # crossing between tasks (arguments, captures, results) keep their
        # counts: the program's own functions call no deep-copy routine
        source = ("struct Job {\n    xs: [int],\n    tags: [str: int],\n}\n\n"
                  "async fun work(j: Job) -> int {\n    return j.xs.len() + j.tags.len()\n}\n\n"
                  "async fun names(n: int) -> [str] {\n    return [\"a\", f\"{n}\"]\n}\n\n"
                  "#main\nasync fun main() {\n    let j = Job { xs: [1, 2, 3], tags: [\"a\": 1] }\n"
                  "    async let a = work(j)\n    async let b = names(4)\n    let c = async () => j.xs.len()\n"
                  "    async let d = c()\n    print(await a + (await b).len() + await d)\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tasks.my")
            with open(path, "w") as fh:
                fh.write(source)
            self.same(path)
            asm = subprocess.run([native_compiler(), path, STDLIB_ROOT, "--target", "wasm32-wasi"], capture_output=True,
                                 text=True, check=True, cwd=_REPO).stdout
        bodies = re.findall(r"^(myla_(?:main|work|names)[A-Za-z0-9_]*):\n(.*?)\n\tend_function", asm, re.M | re.S)
        self.assertGreater(len(bodies), 3)
        for name, body in bodies:
            if name.endswith(("_env_deep", "_env_clone", "_env_drop")):
                continue
            with self.subTest(function=name):
                self.assertEqual(re.findall(r"call \S*(?:deep|dclone)\S*", body), [])

    def test_examples(self):
        for path in sorted(glob.glob(os.path.join(_REPO, "examples", "*.my"))):
            with self.subTest(example=os.path.basename(path)):
                self.same(path)

    def test_programs(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in PROGRAMS.items():
                with self.subTest(program=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w") as fh:
                        fh.write(source.lstrip())
                    self.same(path)

    def test_memory_grows_under_the_runner(self):
        # Node's own WASI crashed when the memory grew between two calls; the
        # runner's shim reads it afresh each time
        source = ("fun main() {\n    var lists: [[int]] = []\n    var k = 0\n    while k < 40 {\n"
                  "        var xs: [int] = []\n        var i = 0\n        while i < 500000 {\n"
                  "            xs.push(i)\n            i += 1\n        }\n        lists.push(xs)\n"
                  "        print(k)\n        k += 1\n    }\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "grow.my")
            with open(path, "w") as fh:
                fh.write(source)
            wb = os.path.join(tmp, "grow.wasm")
            build_wasm(path, wb)
            self.assertEqual(run(NODE + [wb]), ("".join(f"{k}\n" for k in range(40)), "", 0))

    def test_a_list_past_2_27_elements(self):
        # a list stopped at 2^26 elements (the review of 2026-11-06, R6): every
        # cell above 4 KB took a power of two, header and all, and the cells
        # it outgrew stayed; a big cell at the top of the memory now grows
        # where it is (D157)
        source = ("fun main() {\n    var xs: [int64] = []\n    var i: int64 = 0\n"
                  "    while i < 150000000 {\n        xs.push(i)\n        i += 1\n    }\n"
                  "    print(xs.len())\n    print(xs[xs.len() - 1])\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "big.my")
            with open(path, "w") as fh:
                fh.write(source)
            wb = os.path.join(tmp, "big.wasm")
            build_wasm(path, wb)
            self.assertEqual(run(NODE + [wb]), ("150000000\n149999999\n", "", 0))

    def test_files(self):
        # files and directories through WASI: written, read, listed, renamed
        # and removed, a relative path against the working directory
        source = ("import std.fs as fs\n\nfun main() {\n"
                  "    match fs.make_dir(\"wd\") { Ok(n) => {}, Err(e) => { print(\"mkdir failed\") } }\n"
                  "    match fs.write_to_file(\"wd/a.txt\", \"one\\ntwo\\n\") { Ok(()) => { print(\"written\") }, Err(e) => { print(\"write failed\") } }\n"
                  "    match fs.read_to_string(\"wd/a.txt\") { Ok(s) => { print(s.len()) }, Err(e) => { print(\"read failed\") } }\n"
                  "    print(fs.exists(\"wd/a.txt\"))\n    print(fs.is_dir(\"wd\"))\n"
                  "    match fs.rename(\"wd/a.txt\", \"wd/b.txt\") { Ok(n) => {}, Err(e) => { print(\"rename failed\") } }\n"
                  "    match fs.list_dir(\"wd\") { Ok(xs) => { for x in xs { print(x) } }, Err(e) => { print(\"list failed\") } }\n"
                  "    match fs.remove_file(\"wd/b.txt\") { Ok(n) => {}, Err(e) => { print(\"rm failed\") } }\n"
                  "    match fs.remove_dir(\"wd\") { Ok(n) => {}, Err(e) => { print(\"rmdir failed\") } }\n"
                  "    print(fs.exists(\"wd\"))\n"
                  "    match fs.read_to_string(\"missing.txt\") { Ok(s) => { print(s) }, Err(e) => { print(\"missing\") } }\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "files.my")
            with open(path, "w") as fh:
                fh.write(source)
            xb, wb = os.path.join(tmp, "x86"), os.path.join(tmp, "files.wasm")
            build_x86(path, xb)
            build_wasm(path, wb)
            want = subprocess.run([xb], capture_output=True, text=True, cwd=tmp)
            got = subprocess.run(NODE + [wb], capture_output=True, text=True, cwd=tmp)
            self.assertEqual((got.stdout, got.stderr, got.returncode), (want.stdout, want.stderr, want.returncode))
            self.assertIn("8\n", want.stdout)

    def test_compiler(self):
        # the compiler built for wasm makes the same assembly as the one built
        # for x86-64, for either target; without --target, for its own (D127)
        with tempfile.TemporaryDirectory() as tmp:
            gen = os.path.join(tmp, "gen.wasm")
            build_wasm("selfhost/gen_main.my", gen)
            for extra, ref in (([], ["--target", "wasm32-wasi"]),
                               (["--target", "wasm32-wasi"], ["--target", "wasm32-wasi"]),
                               (["--target", "x86_64-linux"], [])):
                with self.subTest(target=extra):
                    src = os.path.join(_REPO, "examples", "maps.my")
                    want = run([native_compiler(), src, STDLIB_ROOT] + ref)
                    got = run(NODE + [gen, src, STDLIB_ROOT] + extra)
                    self.assertEqual(got[2], 0, got[1])
                    self.assertEqual(got, want)

    def test_the_compiler_compiles_itself(self):
        # the whole compiler compiled by the compiler built for wasm, under
        # Node: byte for byte what the native compiler writes, for wasm32
        # (that compiler's own target) and for x86-64 (MYLA-268)
        with tempfile.TemporaryDirectory() as tmp:
            gen = os.path.join(tmp, "gen.wasm")
            build_wasm("selfhost/gen_main.my", gen)
            src = os.path.join(_REPO, "selfhost", "gen_main.my")
            for target in ["wasm32-wasi", "x86_64-linux"]:
                with self.subTest(target=target):
                    want = run([native_compiler(), src, STDLIB_ROOT, "--target", target])
                    got = run(NODE + [gen, src, STDLIB_ROOT, "--target", target])
                    self.assertEqual(got[1:], ("", 0))
                    self.assertEqual(len(got[0]), len(want[0]))
                    self.assertTrue(got[0] == want[0], "the assembly differs")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WASM, WASM_SKIP)
class WasmImports(unittest.TestCase):
    def test_the_import_numbers_agree(self):
        # lib/std/platform_wasm.my numbers the WASI imports it calls (W_FD_WRITE = 1, ...);
        # selfhost/runtime_wasm.my's wasi_calls() lists them in that order, and
        # memory.grow follows them: reordering either silently calls the wrong import
        with open(os.path.join(_REPO, "lib", "std", "platform_wasm.my"), encoding="utf-8") as fh:
            platform = dict(re.findall(r"^const W_([A-Z_]+): int64 = (\d+)$", fh.read(), flags=re.M))
        with open(os.path.join(_REPO, "selfhost", "runtime_wasm.my"), encoding="utf-8") as fh:
            runtime = fh.read()
        calls = re.search(r"fun wasi_calls\(\)[^{]*\{(.*?)\n\}", runtime, flags=re.S).group(1)
        names = re.findall(r'\("([a-z_]+)", "', calls)
        self.assertEqual([platform[n.upper()] for n in names], [str(i + 1) for i in range(len(names))], names)
        grow = re.search(r"^const W_MEMORY_GROW: int32 = (\d+)$", runtime, flags=re.M).group(1)
        self.assertEqual((grow, platform["MEMORY_GROW"]), (str(len(names) + 1), str(len(names) + 1)))


class WasmTasks(unittest.TestCase):
    def test_stress_programs(self):
        # the concurrency stress programs on one worker (D125), in each order
        from .test_concurrency_stress import EXPECTED, SCHEDULES, _DIR
        for name, want in EXPECTED.items():
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                wb = os.path.join(tmp, name + ".wasm")
                build_wasm(os.path.join(_DIR, name + ".my"), wb)
                for extra in [{}] + [{"MYLA_SCHED": sched} for sched in SCHEDULES]:
                    p = subprocess.run(NODE + [wb], capture_output=True, text=True, timeout=120,
                                       env=dict(os.environ, **extra))
                    self.assertEqual((p.stdout, p.returncode), want, extra)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WASM, WASM_SKIP)
class WasmPage(unittest.TestCase):
    """The page API (tools/wasm/myla.mjs over selfhost/play_main.my built for
    wasm, its files in memory) against the native CLI (`myla check`, `myla
    run`, `myla test`)."""

    @classmethod
    def setUpClass(cls):
        from ._tools import selfhost_tool
        cls.myla = selfhost_tool("main")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.play = os.path.join(cls.tmp.name, "play.wasm")
        build_wasm("selfhost/play_main.my", cls.play)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def page(self, requests: list[dict]) -> list[dict]:
        import json
        path = os.path.join(self.tmp.name, "requests.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(requests, fh)
        p = subprocess.run(["node", "--stack-size=7000", os.path.join(_REPO, "tests", "burn", "data", "wasm_page.mjs"), self.play, path],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def native(self, cmd: str, source: str, stdin: str = "", args: list[str] | None = None) -> tuple[str, str, int]:
        # the CLI on the same file, as `main.my` in a directory of its own
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "main.my"), "w", encoding="utf-8") as fh:
                fh.write(source)
            p = subprocess.run([self.myla, cmd, "main.my"] + (args or []), capture_output=True, text=True, cwd=tmp,
                               input=stdin, timeout=120)
            return p.stdout, p.stderr, p.returncode

    def test_check_reports_the_error_corpus(self):
        # each file's errors: their kind, message and position, as `myla
        # check` reports them
        import re
        files = []
        for path in sorted(glob.glob(os.path.join(_REPO, "examples", "errors", "*.my"))):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if "//~ runtime error" in text or "import " in text:
                continue
            files.append((os.path.basename(path), text))
        got = self.page([{"op": "check", "files": text} for _, text in files])
        head = re.compile(r"^((?:lex|parse|module|type) error): (.*)\n  --> main\.my:(\d+):(\d+)$", re.M)
        for (name, text), res in zip(files, got):
            with self.subTest(file=name):
                out, err, code = self.native("check", text)
                want = [(k, m, int(l), int(c)) for k, m, l, c in head.findall(err)]
                errors = [d for d in res["diagnostics"] if d["severity"] == "error"]
                self.assertEqual([(d["kind"], d["message"], d["line"], d["col"]) for d in errors], want)
                self.assertEqual(res["ok"], code == 0)
        self.assertGreater(len(files), 150)

    def test_run_gives_what_the_interpreter_gives(self):
        # every single-file example (but those reading input or files), and
        # its #test cases
        cases = []
        for path in sorted(glob.glob(os.path.join(_REPO, "examples", "*.my"))):
            with open(path, encoding="utf-8") as fh:
                cases.append((os.path.basename(path), fh.read()))
        got = self.page([{"op": "run", "files": t} for _, t in cases] + [{"op": "test", "files": t} for _, t in cases])
        for i, (name, text) in enumerate(cases):
            with self.subTest(example=name):
                out, err, code = self.native("run", text)
                self.assertEqual((got[i]["stdout"], got[i]["stderr"], got[i]["exitCode"]), (out, err, code))
                out, err, code = self.native("test", text)
                t = got[len(cases) + i]
                self.assertEqual((t["stdout"], t["stderr"], t["exitCode"]), (out, err, code))

    def test_input_arguments_modules_and_files(self):
        echo = ("import std.io as io\nfrom std.process import args\nimport std.fs as fs\n\nfun main() {\n"
                "    var r = io.stdin()\n    match r.read_line() { Ok(Some(l)) => { print(\"got \" + l) }, _ => { print(\"none\") } }\n"
                "    for a in args() { print(a) }\n"
                "    match fs.write_to_file(\"out/note.txt\", \"written\") { Ok(()) => { print(\"written\") }, Err(e) => { print(\"no dir\") } }\n"
                "    match fs.make_dir(\"out\") { Ok(n) => {}, Err(e) => { print(\"mkdir failed\") } }\n"
                "    match fs.write_to_file(\"out/note.txt\", \"written\") { Ok(()) => { print(\"written\") }, Err(e) => { print(\"write failed\") } }\n"
                "    let xs = [1]\n    print(xs[3])\n}\n")
        geo = {"main.my": "import geo\n\nfun main() {\n    print(geo.twice(21))\n}\n",
               "geo.my": "pub fun twice(n: int) -> int {\n    return 2 * n\n}\n"}
        got = self.page([{"op": "run", "files": echo, "stdin": "hello\nmore\n", "args": ["a", "b c"], "read": ["out/note.txt"]},
                         {"op": "run", "files": geo}, {"op": "check", "files": geo}])
        self.assertEqual((got[0]["stdout"], got[0]["exitCode"]), ("got hello\nmain.my\na\nb c\nno dir\nwritten\n", 1))
        self.assertEqual(got[0]["stderr"], self.native("run", echo, "hello\nmore\n", ["a", "b c"])[1])
        self.assertEqual(got[0]["read"], {"out/note.txt": "written"})
        self.assertEqual((got[1]["stdout"], got[1]["exitCode"]), ("42\n", 0))
        self.assertEqual(got[2], {"ok": True, "diagnostics": []})

    def test_warnings_and_ranges(self):
        # a warning comes with the errors' fields; an error's range
        warn = "fun main() {\n    print(__clock_ns() > 0)\n}\n"
        bad = "fun main() {\n    let x: int = \"a\"\n}\n"
        got = self.page([{"op": "check", "files": warn}, {"op": "check", "files": bad}])
        out, err, code = self.native("check", warn)
        self.assertEqual(got[0]["ok"], True)
        self.assertEqual([d["severity"] for d in got[0]["diagnostics"]], ["warning"] * err.count("warning:"))
        self.assertEqual(err.count("warning:"), 1)
        w = got[0]["diagnostics"][0]
        self.assertEqual((w["line"], w["col"]), (2, 11))
        self.assertIn("'__clock_ns' is a primitive", w["message"])
        self.assertEqual([n["label"] for n in w["notes"]], ["help"])
        d = got[1]["diagnostics"][0]
        self.assertEqual((d["severity"], d["kind"], d["line"], d["col"], d["endLine"]), ("error", "type error", 2, 5, 2))
        self.assertGreater(d["endCol"], d["col"])


def _have_playwright() -> bool:
    if not shutil.which("node"):
        return False
    p = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True)
    return p.returncode == 0


@unittest.skipUnless(os.environ.get("MYLA_REQUIRE_BROWSER"), "MYLA_REQUIRE_BROWSER is not set")
class BrowserTools(unittest.TestCase):
    """CI's wasm-page job sets MYLA_REQUIRE_BROWSER, so a missing Playwright
    fails there instead of skipping the page's test unnoticed (MYLA-297)."""

    def test_playwright_is_there(self):
        self.assertTrue(_have_playwright(), "the browser test needs Node's playwright with its Chromium")
        self.assertTrue(HAVE_WASM, WASM_SKIP)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WASM, WASM_SKIP)
@unittest.skipUnless(_have_playwright(), "the browser test needs Node's playwright with its Chromium")
class WasmBrowser(unittest.TestCase):
    def test_the_playground_page(self):
        # tools/wasm/page.html in Chromium: its example run, a type error
        # checked and shown, a runtime error and an endless recursion
        # through the API, nothing logged as an error
        import json
        with tempfile.TemporaryDirectory() as tmp:
            for f in ("page.html", "myla.mjs", "wasi.mjs", "mem_fs.mjs"):
                shutil.copy(os.path.join(_REPO, "tools", "wasm", f), tmp)
            build_wasm("selfhost/play_main.my", os.path.join(tmp, "play.wasm"))
            p = subprocess.run(["node", os.path.join(_REPO, "tests", "burn", "data", "wasm_browser.js"), tmp],
                               capture_output=True, text=True, timeout=300)
            self.assertEqual(p.returncode, 0, p.stderr)
            got = json.loads(p.stdout)
        self.assertEqual(got["run"], {"stdout": "0\n1\n1\n2\n3\n5\n8\n13\n21\n34\n", "exitCode": 0})
        self.assertEqual(got["check"]["ok"], False)
        self.assertEqual(got["shown"], "2:5 type error: cannot assign value of type 'str' to binding of type 'int32'")
        self.assertEqual(got["more"]["a"][1], 1)
        self.assertTrue(got["more"]["a"][0].startswith("runtime error: list index 2 out of bounds (len 1)\n  --> main.my:3:13\n"))
        self.assertEqual(got["more"]["b"], ["runtime error: stack overflow\n", 1])
        self.assertEqual(got["errors"], [])


# MYLA-261: a recursion whose frames are large runs out of the shadow stack
# (`__stack_pointer`, in memory) before the engine's call stack; one whose
# frames are small runs out of the engine's first
BIG_FRAMES = """
struct Q {
    a: int64, b: int64, c: int64, d: int64, e: int64, f: int64, g: int64, h: int64,
}

struct R {
    x: Q, y: Q, z: Q, w: Q,
}

fun down(n: int64, q: Q) -> int64 {
    let r = R { x: q, y: q, z: q, w: q }
    let s = R { x: r.y, y: r.z, z: r.w, w: r.x }
    let t = R { x: s.y, y: s.z, z: s.w, w: s.x }
    let u = R { x: t.y, y: t.z, z: t.w, w: t.x }
    let v = Q { a: u.x.a + 1, b: u.y.b, c: u.z.c, d: u.w.d, e: q.e, f: q.f, g: q.g, h: q.h }
    if n == 0 {
        return v.a
    }
    return down(n - 1, v) + 1
}

fun main() {
    let q = Q { a: 0, b: 0, c: 0, d: 0, e: 0, f: 0, g: 0, h: 0 }
    print(down(1000, q))
    print("the data is intact")
    print(down(100000000, q))
}
"""

SMALL_FRAMES = """
fun down(n: int) -> int {
    if n == 0 {
        return 0
    }
    return down(n - 1) + 1
}

fun main() {
    print(down(1000))
    print(down(100000000))
}
"""


def _leb(b: bytes, i: int) -> tuple[int, int]:
    v = shift = 0
    while True:
        x = b[i]
        i += 1
        v |= (x & 0x7F) << shift
        shift += 7
        if x < 0x80:
            return v, i


def stack_and_data(path: str) -> tuple[int, list[int]]:
    """A module's first global's start value (wasm-ld's `__stack_pointer`)
    and the start of each active data segment."""
    with open(path, "rb") as fh:
        b = fh.read()
    i, sp, data = 8, -1, []
    while i < len(b):
        sid = b[i]
        size, i = _leb(b, i + 1)
        end = i + size
        if sid == 6 and sp < 0:              # globals: type, mutability, i32.const n
            _, j = _leb(b, i)
            assert b[j + 2] == 0x41
            sp, _ = _leb(b, j + 3)
        if sid == 11:                         # data: flags 0, i32.const n, end, bytes
            n, j = _leb(b, i)
            for _ in range(n):
                assert b[j] == 0 and b[j + 1] == 0x41
                off, j = _leb(b, j + 2)
                data.append(off)
                ln, j = _leb(b, j + 1)
                j += ln
        i = end
    return sp, data


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WASM, WASM_SKIP)
class WasmStack(unittest.TestCase):
    """Running out of the stack on wasm is the runtime error it is natively
    (MYLA-261): never a write over the static data, never the engine's own
    trap message."""

    def same(self, tmp: str, name: str, source: str) -> None:
        """The program built for wasm gives what its x86-64 build gives,
        which runs out of its stack too."""
        path = os.path.join(tmp, name + ".my")
        with open(path, "w") as fh:
            fh.write(source.lstrip())
        out = os.path.join(tmp, name + ".wasm")
        build_wasm(path, out)
        build_x86(path, os.path.join(tmp, name))
        want = run([os.path.join(tmp, name)])
        self.assertEqual(want[1:], ("runtime error: stack overflow\n", 1))
        self.assertEqual(run(NODE + [out]), want)

    def test_the_stack_lies_below_the_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hello.wasm")
            build_wasm(os.path.join(_REPO, "examples", "hello.my"), path)
            sp, data = stack_and_data(path)
            self.assertTrue(data)
            self.assertLessEqual(sp, min(data))

    def test_running_out_of_the_shadow_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.same(tmp, "big", BIG_FRAMES)

    def test_running_out_of_the_engines_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.same(tmp, "small", SMALL_FRAMES)



# D129: what wasm32 can't do is a cause of its own, `Unsupported`
UNSUPPORTED = """
from std.process import run, SpawnError
from std.fs import read_to_string, IoError

fun main() {
    print(match run("/bin/true", []) {
        Ok(o) => "ran",
        Err(SpawnError.Unsupported) => "unsupported",
        Err(e) => "another error",
    })
    print(match read_to_string("/no/such/file") {
        Ok(s) => "read",
        Err(IoError.NotFound) => "not found",
        Err(e) => "another error",
    })
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(HAVE_WASM, WASM_SKIP)
class WasmCapabilities(unittest.TestCase):
    def test_no_processes_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "unsupported.my")
            with open(path, "w") as fh:
                fh.write(UNSUPPORTED.lstrip())
            out = os.path.join(tmp, "unsupported.wasm")
            build_wasm(path, out)
            self.assertEqual(run(NODE + [out]), ("unsupported\nnot found\n", "", 0))

@unittest.skipUnless(HAVE_WASM, WASM_SKIP)
class WasmTime(test_time.Time):
    """test_time's programs built for wasm and run under Node (through a
    script, as the tests run the binary), on one worker whatever
    MYLA_THREADS says. Not the ones that read slow input or start a child
    process: WASI has no processes, and the shim counts a watched input as
    ready at once (a read blocks)."""

    def native(self, name: str, text: str) -> str:
        exe = os.path.join(self.dir, name)
        build_wasm(self.source(name, text), exe + ".wasm")
        with open(exe, "w", encoding="utf-8") as fh:
            fh.write(f'#!/bin/sh\nexec node --stack-size=7000 "{RUNNER}" "{exe}.wasm" "$@"\n')
        os.chmod(exe, 0o755)
        return exe

    def test_an_async_read_lets_the_other_tasks_run(self):
        self.skipTest("the WASI shim can't wait for input without blocking")

    def test_a_time_limit_around_a_read(self):
        self.skipTest("the WASI shim can't wait for input without blocking")

    def test_a_child_process_waited_for_without_blocking_the_worker(self):
        self.skipTest("WASI has no processes")

    def test_child_processes_waited_for_by_programs_running_at_once(self):
        self.skipTest("WASI has no processes")

    def test_the_virtual_clock_takes_no_time(self):
        self.skipTest("the interpreter's, tested in test_time")


if __name__ == "__main__":
    unittest.main()
