"""Unit tests for the filesystem runtime (v0.5.4c, D29).

Covers the low-level `__read_file`/`__io_errno` primitives as the type checker
sees them, and the public `std.fs.read_to_string -> Result<str, IoError>`
surface run through the interpreter (real file IO, errno-keyed errors). The
directory primitives `__list_dir`, `__mkdir` and `__stat` and their `std.fs`
wrappers (MYLA-88) are covered the same way, and so are `__getcwd` and
`current_dir` (MYLA-98); `FS_TOUR` and `CWD_PROGRAM` are also run by every
implementation in `tests/burn/test_fs.py`."""
import io
import os
import tempfile
import unittest

from myla.errors import TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.loader import default_stdlib_root, link
from myla.parser import parse
from myla.types import check


def check_src(src: str):
    return check(parse(tokenize(src)))


def link_and_run(src: str, files: dict | None = None) -> tuple[str, str, int]:
    """Write `src` (plus any `files` mapping name->contents) into a temp dir,
    link against the bundled stdlib, and run through the interpreter. Returns
    (stdout, stderr, exit). Program paths can reference data files by name
    relative to the temp dir via the returned `{dir}` substitution."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, contents in (files or {}).items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                fh.write(contents)
        path = os.path.join(tmp, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src.replace("{dir}", tmp))
        checker = check(link(path, stdlib_root=default_stdlib_root()))
        out, err = io.StringIO(), io.StringIO()
        code = Interpreter(checker, out, err).run()
        return out.getvalue(), err.getvalue(), code


class TestRuntimePrimitives(unittest.TestCase):
    def test_read_file_accepts_path(self):
        check_src('fun main() { let s = __read_file("p") }\n')

    def test_read_file_rejects_non_string(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun main() { let s = __read_file(42) }\n")

    def test_read_file_rejects_wrong_arity(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun main() { let s = __read_file() }\n")

    def test_io_errno_rejects_arguments(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun main() { let e = __io_errno(1) }\n")

    def test_write_file_accepts_path_and_contents(self):
        check_src('fun main() { __write_file("p", "data") }\n')

    def test_write_file_rejects_non_string_path(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { __write_file(42, "data") }\n')

    def test_write_file_rejects_non_string_contents(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { __write_file("p", 42) }\n')

    def test_write_file_rejects_wrong_arity(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { __write_file("p") }\n')


class TestWriteToFile(unittest.TestCase):
    def test_write_then_read_round_trips(self):
        out, _, code = link_and_run(
            "from std.io import write\n"
            "from std.fs import write_to_file, read_to_string, IoError\n"
            "fun main() {\n"
            '    match write_to_file("{dir}/out.txt", "héllo\\nλ\\n") {\n'
            "        Ok(n) => print(n),\n"           # bytes written (byte length)
            '        Err(e) => print(-1),\n'
            "    }\n"
            '    match read_to_string("{dir}/out.txt") {\n'
            "        Ok(s) => write(1, s),\n"
            '        Err(e) => write(2, "read-fail"),\n'
            "    }\n"
            "}\n",
        )
        # "héllo\nλ\n" is 10 bytes (é=2, λ=2), then the file content verbatim.
        self.assertEqual(out, "10\nhéllo\nλ\n")
        self.assertEqual(code, 0)

    def test_write_to_missing_dir_is_error(self):
        out, _, _ = link_and_run(
            "from std.io import println\n"
            "from std.fs import write_to_file, IoError\n"
            "fun describe(e: IoError) -> str {\n"
            "    return match e {\n"
            '        IoError.NotFound => "not-found",\n'
            '        IoError.PermissionDenied => "denied",\n'
            '        IoError.Other(c) => "other",\n'
            "    }\n"
            "}\n"
            "fun main() {\n"
            '    match write_to_file("{dir}/nope/out.txt", "x") {\n'
            '        Ok(n) => println("unexpected"),\n'
            "        Err(e) => println(describe(e)),\n"
            "    }\n"
            "}\n",
        )
        self.assertEqual(out, "not-found\n")


class TestReadToString(unittest.TestCase):
    def test_reads_whole_file(self):
        out, _, _ = link_and_run(
            "from std.io import println\n"
            "from std.fs import read_to_string, IoError\n"
            "fun main() {\n"
            '    match read_to_string("{dir}/data.txt") {\n'
            "        Ok(s) => println(s),\n"
            '        Err(e) => println("err"),\n'
            "    }\n"
            "}\n",
            files={"data.txt": "line one\nλ done\n"},
        )
        self.assertEqual(out, "line one\nλ done\n\n")  # file text + println's \n

    def test_byte_length_matches(self):
        out, _, _ = link_and_run(
            "from std.fs import read_to_string, IoError\n"
            "fun main() {\n"
            '    match read_to_string("{dir}/data.txt") {\n'
            "        Ok(s) => print(len(s)),\n"
            "        Err(e) => print(-1),\n"
            "    }\n"
            "}\n",
            files={"data.txt": "héllo"},   # 6 bytes (é is 2)
        )
        self.assertEqual(out, "6\n")

    def test_missing_file_is_not_found(self):
        out, _, _ = link_and_run(
            "from std.io import println\n"
            "from std.fs import read_to_string, IoError\n"
            "fun describe(e: IoError) -> str {\n"
            "    return match e {\n"
            '        IoError.NotFound => "not-found",\n'
            '        IoError.PermissionDenied => "denied",\n'
            '        IoError.Other(c) => "other",\n'
            "    }\n"
            "}\n"
            "fun main() {\n"
            '    match read_to_string("{dir}/absent.txt") {\n'
            '        Ok(s) => println("unexpected"),\n'
            "        Err(e) => println(describe(e)),\n"
            "    }\n"
            "}\n",
        )
        self.assertEqual(out, "not-found\n")

    def test_try_propagates_error(self):
        out, _, _ = link_and_run(
            "from std.io import println\n"
            "from std.fs import read_to_string, IoError\n"
            "fun size(path: str) -> Result<int32, IoError> {\n"
            "    let s = read_to_string(path)?\n"
            "    return Ok(len(s) as int32)\n"
            "}\n"
            "fun main() {\n"
            '    match size("{dir}/absent.txt") {\n'
            '        Ok(n) => println("ok"),\n'
            '        Err(e) => println("propagated"),\n'
            "    }\n"
            "}\n",
        )
        self.assertEqual(out, "propagated\n")

    def test_read_to_string_type_is_result(self):
        from myla import ast
        from myla.types import EnumType
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "main.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("from std.fs import read_to_string\n"
                         'fun main() { let r = read_to_string("x") }\n')
            checker = check(link(path, stdlib_root=default_stdlib_root()))
        main = next(d for d in checker.program.decls
                    if isinstance(d, ast.FunDecl) and d.name == "main")
        init = main.body.statements[0].init
        self.assertIsInstance(init.resolved_type, EnumType)
        self.assertEqual(init.resolved_type.name, "Result")


# Every directory function of `std.fs` on relative paths, so it can run in a
# fresh working directory (MYLA-88). `tests/burn/test_fs.py` runs it in all
# four implementations.
FS_TOUR = """from std.io import println
from std.fs import list_dir, make_dir, make_dir_all, exists, is_dir, is_file, write_to_file, IoError

fun describe(e: IoError) -> str {
    return match e {
        IoError.NotFound => "not found"
        IoError.PermissionDenied => "permission denied"
        IoError.Other(code) => format("errno {}", code)
    }
}

fun joined(names: [str]) -> str {
    var sb = StringBuilder()
    for n in names {
        if len(sb) > 0 { append(sb, ",") }
        append(sb, n)
    }
    return build(sb)
}

fun show(label: str, r: Result<[str], IoError>) {
    match r {
        Ok(names) => { println(format("{}: {} [{}]", label, len(names), joined(names))) },
        Err(e) => { println(format("{}: {}", label, describe(e))) },
    }
}

fun made(label: str, r: Result<int32, IoError>) {
    match r {
        Ok(n) => { println(format("{}: ok {}", label, n)) },
        Err(e) => { println(format("{}: {}", label, describe(e))) },
    }
}

fun kind(path: str) {
    println(format("'{}': exists {} dir {} file {}", path, exists(path), is_dir(path), is_file(path)))
}

fun touch(path: str) {
    match write_to_file(path, path) {
        Ok(n) => {},
        Err(e) => { println(format("write {}: {}", path, describe(e))) },
    }
}

fun main() {
    show("empty", list_dir("."))
    made("make a", make_dir("a"))
    made("make a again", make_dir("a"))
    made("make in missing", make_dir("missing/b"))
    made("make all", make_dir_all("deep/er/est"))
    made("make all again", make_dir_all("deep/er/est"))
    made("make all trailing", make_dir_all("deep/er/est2/"))
    for name in ["zeta.txt", "Alpha", "beta", "λ.my", "_under", "10", "9", ".hidden", "a b"] {
        touch("a/" + name)
    }
    made("make sub", make_dir("a/sub"))
    show("a", list_dir("a"))
    show("a/", list_dir("a/"))
    show("deep", list_dir("deep/er"))
    show("file", list_dir("a/beta"))
    show("missing", list_dir("missing"))
    made("make all through a file", make_dir_all("a/beta/c"))
    made("make all over a file", make_dir_all("a/beta"))
    kind(".")
    kind("a")
    kind("a/beta")
    kind("a/sub/")
    kind("missing")
    kind("a/beta/x")
    kind("")
    made("make many", make_dir("many"))
    var i = 0
    while i < 300 {
        touch(format("many/entry-number-{}-with-a-longer-name.txt", i))
        i = i + 1
    }
    match list_dir("many") {
        Ok(names) => { println(format("many: {} first {} last {}", len(names), names[0], names[len(names) - 1])) },
        Err(e) => { println(format("many: {}", describe(e))) },
    }
}
"""

FS_TOUR_OUTPUT = """empty: 0 []
make a: ok 0
make a again: errno 17
make in missing: not found
make all: ok 0
make all again: ok 0
make all trailing: ok 0
make sub: ok 0
a: 10 [.hidden,10,9,Alpha,_under,a b,beta,sub,zeta.txt,λ.my]
a/: 10 [.hidden,10,9,Alpha,_under,a b,beta,sub,zeta.txt,λ.my]
deep: 2 [est,est2]
file: errno 20
missing: not found
make all through a file: errno 20
make all over a file: errno 17
'.': exists true dir true file false
'a': exists true dir true file false
'a/beta': exists true dir false file true
'a/sub/': exists true dir true file false
'missing': exists false dir false file false
'a/beta/x': exists false dir false file false
'': exists false dir false file false
make many: ok 0
many: 300 first entry-number-0-with-a-longer-name.txt last entry-number-99-with-a-longer-name.txt
"""


def run_in_empty_dir(src: str) -> tuple[str, str, int]:
    """Run `src` through the interpreter with an empty temporary directory as
    the working directory."""
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as prog_dir, tempfile.TemporaryDirectory() as work:
        path = os.path.join(prog_dir, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        checker = check(link(path, stdlib_root=default_stdlib_root()))
        out, err = io.StringIO(), io.StringIO()
        os.chdir(work)
        try:
            code = Interpreter(checker, out, err).run()
        finally:
            os.chdir(cwd)
        return out.getvalue(), err.getvalue(), code


class TestDirectoryPrimitives(unittest.TestCase):
    """The type rules and behaviour of `__list_dir`, `__mkdir` and `__stat`
    (MYLA-88)."""

    def test_accepted(self):
        check_src('fun main() { let s: str = __list_dir(".") }\n')
        check_src('fun main() { __mkdir("d", 493) }\n')
        check_src('fun main() { let m: int32 = __stat(".") }\n')

    def test_rejected(self):
        cases = {
            "__list_dir()": "__list_dir() takes (path: str)",
            "__list_dir(1)": "__list_dir() path must be a string, found 'int32'",
            '__mkdir("d")': "__mkdir() takes (path: str, mode: int32)",
            "__mkdir(1, 2)": "__mkdir() path must be a string, found 'int32'",
            '__mkdir("d", "x")': "__mkdir() mode must be an integer, found 'str'",
            '__stat("a", "b")': "__stat() takes (path: str)",
            "__stat(true)": "__stat() path must be a string, found 'bool'",
        }
        for call, message in cases.items():
            with self.subTest(call=call):
                with self.assertRaises(TypeCheckError) as ctx:
                    check_src(f"fun main() {{ let x = {call} }}\n")
                self.assertIn(message, str(ctx.exception))

    def test_list_dir_gives_names_each_ending_in_nul(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ["b", "a"]:
                open(os.path.join(tmp, name), "w").close()
            out, _, _ = link_and_run(
                "fun main() {\n"
                f'    let raw = __list_dir("{tmp}")\n'
                "    print(__io_errno())\n"
                "    var nuls = 0\n"
                "    var i = 0\n"
                "    while i < len(raw) {\n"
                "        if raw[i] == 0 { nuls = nuls + 1 }\n"
                "        i = i + 1\n"
                "    }\n"
                "    print(raw[len(raw) - 1] == 0)\n"
                "    print(len(raw) - nuls >= 2)\n"
                '    let none = __list_dir("/no/such/dir")\n'
                "    print(__io_errno())\n"
                "    print(len(none))\n"
                "}\n")
        self.assertEqual(out, "0\ntrue\ntrue\n2\n0\n")

    def test_stat_and_mkdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _, _ = link_and_run(
                "fun main() {\n"
                f'    print(__stat("{tmp}") & 0xF000)\n'
                '    print(__stat("/no/such/path"))\n'
                "    print(__io_errno())\n"
                f'    __mkdir("{tmp}/d", 493)\n'
                "    print(__io_errno())\n"
                f'    print(__stat("{tmp}/d") & 0xF000)\n'
                f'    __mkdir("{tmp}/d", 493)\n'
                "    print(__io_errno())\n"
                "}\n")
        self.assertEqual(out, "16384\n-1\n2\n0\n16384\n17\n")


class TestDirectoryFunctions(unittest.TestCase):
    """`std.fs`'s `list_dir`, `make_dir`, `make_dir_all`, `exists`, `is_dir`
    and `is_file` in the interpreter (MYLA-88)."""

    def test_tour(self):
        out, err, code = run_in_empty_dir(FS_TOUR)
        self.assertEqual((err, code), ("", 0))
        self.assertEqual(out, FS_TOUR_OUTPUT)

    def test_order_is_by_bytes(self):
        names = ["zeta.txt", "Alpha", "beta", "λ.my", "_under", "10", "9", ".hidden", "a b", "sub"]
        self.assertEqual(FS_TOUR_OUTPUT.splitlines()[8],
                         f"a: 10 [{','.join(sorted(names, key=str.encode))}]")

    def test_try_composes(self):
        out, _, _ = run_in_empty_dir(
            "from std.fs import list_dir, make_dir, IoError\n"
            "fun count(path: str) -> Result<int32, IoError> {\n"
            "    make_dir(path)?\n"
            "    let names = list_dir(path)?\n"
            "    return Ok(len(names))\n"
            "}\n"
            "fun main() {\n"
            '    match count("x") { Ok(n) => print(n), Err(e) => print(-1) }\n'
            '    match count("x") { Ok(n) => print(n), Err(e) => print(-2) }\n'
            "}\n")
        self.assertEqual(out, "0\n-2\n")


# Prints the working directory twice: `current_dir`'s result, and whether it
# names a directory (MYLA-98). `tests/burn/test_fs.py` runs it in all four
# implementations, in a directory that exists and in one that was removed.
CWD_PROGRAM = """from std.io import println
from std.fs import current_dir, is_dir, IoError

fun main() {
    match current_dir() {
        Ok(d) => { println(format("{} {}", d, is_dir(d))) },
        Err(e) => {
            match e {
                IoError.NotFound => { println("not found") },
                IoError.PermissionDenied => { println("permission denied") },
                IoError.Other(code) => { println(format("errno {}", code)) },
            }
        },
    }
}
"""


class TestCurrentDir(unittest.TestCase):
    """`__getcwd` and `std.fs.current_dir` (MYLA-98)."""

    def test_type_rules(self):
        check_src('fun main() { let s: str = __getcwd() }\n')
        with self.assertRaises(TypeCheckError) as ctx:
            check_src('fun main() { let s = __getcwd(".") }\n')
        self.assertIn("__getcwd() takes no arguments", str(ctx.exception))

    def test_primitive_gives_the_working_directory(self):
        with tempfile.TemporaryDirectory() as work:
            cwd = os.getcwd()
            os.chdir(work)
            try:
                out, _, _ = link_and_run(
                    "fun main() {\n"
                    "    let d = __getcwd()\n"
                    "    print(__io_errno())\n"
                    "    print(d)\n"
                    "}\n")
            finally:
                os.chdir(cwd)
            self.assertEqual(out, f"0\n{os.path.realpath(work)}\n")

    def test_current_dir(self):
        with tempfile.TemporaryDirectory() as work:
            cwd = os.getcwd()
            os.chdir(work)
            try:
                out, err, code = link_and_run(CWD_PROGRAM)
            finally:
                os.chdir(cwd)
            self.assertEqual((out, err, code), (f"{os.path.realpath(work)} true\n", "", 0))

    def test_removed_directory_is_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            gone = os.path.join(tmp, "gone")
            os.mkdir(gone)
            cwd = os.getcwd()
            os.chdir(gone)
            os.rmdir(gone)
            try:
                out, err, code = link_and_run(CWD_PROGRAM)
            finally:
                os.chdir(cwd)
            self.assertEqual((out, err, code), ("not found\n", "", 0))


if __name__ == "__main__":
    unittest.main()
