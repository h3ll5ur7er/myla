"""Burn tests for the filesystem runtime (v0.5.4c, D29).

`std.fs.read_to_string` is exercised end-to-end: the committed `examples/readfile`
program (which also uses argv, the I/O streams, and exit) plus focused parity
programs are linked against the bundled stdlib and run through both the
interpreter and the native compiler, which must agree on stdout, stderr, and the
process exit status — including the errno-keyed `IoError` paths. (The
interpreter's answers are the retired Python interpreter's, recorded; MYLA-219.)

The directory functions (`list_dir`, `make_dir`, `make_dir_all`, `exists`,
`is_dir`, `is_file`; MYLA-88) are run in the self-hosted interpreter and the
self-hosted native backend, each in a fresh working directory; so is
`current_dir` (MYLA-98), also in a working directory that was removed. (They
ran in the Python interpreter and the Python native backend too until those
were retired, MYLA-219.)"""
import os
import subprocess
import tempfile
import unittest

from ._native import (
    CAN_BUILD_NATIVE,
    SKIP_REASON,
    assemble,
    run_argv,
    target_flags,
    build_and_run_full,
    check_file,
    interpret_full,
    run_file_both_now,
    run_source_both_now,
    write_program,
)
from ._tools import STDLIB_ROOT, selfhost_tool

EXAMPLE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                 "examples", "readfile", "main.my")
)
POEM = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                 "examples", "readfile", "poem.txt")
)
POEM_TEXT = "roses are red\nλ is a letter\n😀 is not\n"


def _run_both(source: str, args=None):
    """Link/check `source`, run it through both backends with the same argv, and
    return the agreed (stdout, stderr, exit). Asserts the backends match."""
    argv0 = "prog"
    program_argv = [argv0, *(args or [])]
    with tempfile.TemporaryDirectory() as tmp:
        path = write_program(tmp, source)
        interp = interpret_full(check_file(path), argv=program_argv)
        native = build_and_run_full(check_file(path), args=args, argv0=argv0)
    assert interp == native, f"interpreter {interp!r} != native {native!r}"
    return interp


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestReadFileExample(unittest.TestCase):
    # The example's error causes changed with D129, so these are its own
    # expectations, not the retired toolchain's recorded answers.
    def test_echoes_the_file(self):
        self.assertEqual(run_file_both_now(EXAMPLE, [POEM]), (POEM_TEXT, "", 0))

    def test_missing_file(self):
        self.assertEqual(run_file_both_now(EXAMPLE, ["/no/such/file"]), ("", "no such file\n", 1))

    def test_a_directory(self):
        self.assertEqual(run_file_both_now(EXAMPLE, ["/"]), ("", "a directory, not a file\n", 1))

    def test_missing_argument(self):
        self.assertEqual(run_file_both_now(EXAMPLE, []), ("", "usage: readfile <path>\n", 2))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestReadToStringParity(unittest.TestCase):
    def test_reads_committed_file(self):
        # The poem path is absolute, so it resolves the same for both backends.
        out, err, code = _run_both(
            "from std.io import write\n"
            "from std.fs import read_to_string, IoError\n"
            "fun main() {\n"
            f'    match read_to_string("{POEM}") {{\n'
            "        Ok(s) => write(1, s),\n"
            '        Err(e) => write(2, "err"),\n'
            "    }\n"
            "}\n",
        )
        self.assertEqual((out, err, code), (POEM_TEXT, "", 0))

    def test_byte_length_parity(self):
        out, _, _ = _run_both(
            "from std.fs import read_to_string, IoError\n"
            "fun main() {\n"
            f'    match read_to_string("{POEM}") {{\n'
            "        Ok(s) => print(s.len()),\n"
            "        Err(e) => print(-1),\n"
            "    }\n"
            "}\n",
        )
        self.assertEqual(out, f"{len(POEM_TEXT.encode('utf-8'))}\n")

    def test_not_found_errno_parity(self):
        out, _, _ = run_source_both_now(
            "from std.io import println\n"
            "from std.fs import read_to_string, IoError\n"
            "fun describe(e: IoError) -> str {\n"
            "    return match e {\n"
            '        IoError.NotFound => "not-found",\n'
            '        IoError.PermissionDenied => "denied",\n'
            '        _ => "other",\n'
            "    }\n"
            "}\n"
            "fun main() {\n"
            '    match read_to_string("/definitely/not/here") {\n'
            '        Ok(s) => println("?"),\n'
            "        Err(e) => println(describe(e)),\n"
            "    }\n"
            "}\n",
        )
        self.assertEqual(out, "not-found\n")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestWriteToFileParity(unittest.TestCase):
    def test_write_then_read_round_trip_parity(self):
        # Each backend writes the file then reads it back within its own run, so
        # a fixed path is safe; both must produce the same round-tripped output.
        path = os.path.join(tempfile.gettempdir(), "myla_burn_wtf.txt")
        out, err, code = run_source_both_now(
            "from std.io import write\n"
            "from std.fs import write_to_file, read_to_string, IoError\n"
            "fun main() {\n"
            f'    match write_to_file("{path}", "abc\\nλ done\\n") {{\n'
            '        Ok(()) => print("written"),\n'
            "        Err(e) => print(-1),\n"
            "    }\n"
            f'    match read_to_string("{path}") {{\n'
            "        Ok(s) => write(1, s),\n"
            '        Err(e) => write(2, "read-fail"),\n'
            "    }\n"
            "}\n",
        )
        # `Ok(())` once written (D138), then the verbatim file content
        self.assertEqual((out, err, code), ("written\nabc\nλ done\n", "", 0))

    def test_write_to_missing_dir_errno_parity(self):
        out, _, _ = run_source_both_now(
            "from std.io import println\n"
            "from std.fs import write_to_file, IoError\n"
            "fun describe(e: IoError) -> str {\n"
            "    return match e {\n"
            '        IoError.NotFound => "not-found",\n'
            '        IoError.PermissionDenied => "denied",\n'
            '        _ => "other",\n'
            "    }\n"
            "}\n"
            "fun main() {\n"
            '    match write_to_file("/no/such/dir/out.txt", "x") {\n'
            '        Ok(n) => println("?"),\n'
            "        Err(e) => println(describe(e)),\n"
            "    }\n"
            "}\n",
        )
        self.assertEqual(out, "not-found\n")


    def test_directory_read_is_a_directory(self):
        # Opening a directory succeeds but reading it fails with EISDIR, which
        # is IoError.IsADirectory (D129) in both implementations.
        out, _, _ = run_source_both_now(
            "from std.fs import read_to_string, IoError\n"
            "fun code_of(e: IoError) -> int32 {\n"
            "    return match e {\n"
            "        IoError.IsADirectory => 21,\n"
            "        _ => -1,\n"
            "    }\n"
            "}\n"
            "fun main() {\n"
            '    match read_to_string("/") {\n'
            "        Ok(s) => print(-2),\n"
            "        Err(e) => print(code_of(e)),\n"
            "    }\n"
            "}\n",
        )
        self.assertEqual(out, "21\n")   # EISDIR on Linux


# Every directory function of `std.fs` on relative paths, so it can run in a
# fresh working directory (MYLA-88). It was shared with the unit tests of the
# retired Python toolchain; `DirectoryParity` runs it in both implementations.
FS_TOUR = """from std.io import println
from std.fs import list_dir, make_dir, make_dir_all, exists, is_dir, is_file, write_to_file, IoError

fun describe(e: IoError) -> str {
    return match e {
        IoError.NotFound => "not found"
        IoError.PermissionDenied => "permission denied"
        IoError.AlreadyExists => "already exists"
        IoError.NotADirectory => "not a directory"
        IoError.IsADirectory => "is a directory"
        IoError.NotEmpty => "not empty"
        IoError.Other(code) => format("errno {}", code)
        _ => "other"
    }
}

fun joined(names: [str]) -> str {
    var sb = StringBuilder()
    for n in names {
        if sb.len() > 0 { sb.append(",") }
        sb.append(n)
    }
    return sb.build()
}

fun show(label: str, r: Result<[str], IoError>) {
    match r {
        Ok(names) => { println(format("{}: {} [{}]", label, names.len(), joined(names))) },
        Err(e) => { println(format("{}: {}", label, describe(e))) },
    }
}

fun made(label: str, r: Result<(), IoError>) {
    match r {
        Ok(()) => { println(format("{}: ok", label)) },
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
        Ok(names) => { println(format("many: {} first {} last {}", names.len(), names[0], names[names.len() - 1])) },
        Err(e) => { println(format("many: {}", describe(e))) },
    }
}
"""

FS_TOUR_OUTPUT = """empty: 0 []
make a: ok
make a again: already exists
make in missing: not found
make all: ok
make all again: ok
make all trailing: ok
make sub: ok
a: 10 [.hidden,10,9,Alpha,_under,a b,beta,sub,zeta.txt,λ.my]
a/: 10 [.hidden,10,9,Alpha,_under,a b,beta,sub,zeta.txt,λ.my]
deep: 2 [est,est2]
file: not a directory
missing: not found
make all through a file: not a directory
make all over a file: already exists
'.': exists true dir true file false
'a': exists true dir true file false
'a/beta': exists true dir false file true
'a/sub/': exists true dir true file false
'missing': exists false dir false file false
'a/beta/x': exists false dir false file false
'': exists false dir false file false
make many: ok
many: 300 first entry-number-0-with-a-longer-name.txt last entry-number-99-with-a-longer-name.txt
"""

# Prints the working directory twice: `current_dir`'s result, and whether it
# names a directory (MYLA-98). `DirectoryParity` runs it in both
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
                _ => { println("other") },
            }
        },
    }
}
"""


# A directory with many entries of every length from 1 to 255 bytes (the
# longest name Linux allows), so getdents64 fills its buffer many times and
# the native result grows several times over.
MANY = """from std.fs import list_dir
from std.io import println
fun main() {
    match list_dir("big") {
        Ok(names) => {
            var total = 0
            for n in names { total = total + n.len() }
            println(format("{} names, {} bytes", names.len(), total))
            for n in names { println(n) }
        },
        Err(e) => { println("error") },
    }
}
"""


# Removing and renaming (MYLA-96): files, empty and full directories, a
# tree holding a symbolic link to a directory outside it (removed, not
# followed), and the errors.
REMOVE_TOUR = """from std.fs import write_to_file, make_dir, remove_file, remove_dir, remove_dir_all, rename, exists, IoError
from std.io import println
fun code(r: Result<(), IoError>) -> str {
    return match r {
        Ok(()) => "ok"
        Err(e) => match e {
            IoError.NotFound => "not found"
            IoError.PermissionDenied => "denied"
            IoError.IsADirectory => "is a directory"
            IoError.NotEmpty => "not empty"
            IoError.Other(c) => format("errno {}", c)
            _ => "other"
        }
    }
}
fun main() {
    write_to_file("a.txt", "hello")
    println(code(rename("a.txt", "b.txt")))
    let a = exists("a.txt")
    let b = exists("b.txt")
    println(format("{} {}", a, b))
    println(code(remove_file("b.txt")))
    println(code(remove_file("b.txt")))
    make_dir("d")
    println(code(remove_file("d")))
    write_to_file("d/f", "x")
    println(code(remove_dir("d")))
    println(code(remove_dir_all("tree")))
    print(exists("tree"))
    print(exists("outside/keep"))
    println(code(remove_dir_all("missing")))
    println(code(remove_dir_all("d")))
    print(exists("d"))
    println(code(rename("nothere", "x")))
    make_dir("e")
    println(code(remove_dir("e")))
}
"""
REMOVE_TOUR_OUTPUT = "ok\nfalse true\nok\nnot found\nis a directory\nnot empty\nok\nfalse\ntrue\nnot found\nok\nfalse\nnot found\nok\n"


# A path with a NUL byte names nothing (the review of 2026-11-06, R7: the
# kernel read it up to the NUL, so "q\u{0}zzz" wrote "q"): every entry point
# fails with `InvalidInput` and touches no file.
NUL_PATHS = """from std.fs import write_to_file, read_to_string, make_dir, remove_file, remove_dir, rename, exists, list_dir, IoError
fun cause(e: IoError) -> str {
    return match e {
        IoError.InvalidInput => "invalid input",
        IoError.NotFound => "not found",
        _ => "other",
    }
}
fun unit(r: Result<(), IoError>) -> str {
    return match r {
        Ok(()) => "ok",
        Err(e) => cause(e),
    }
}
fun main() {
    print(unit(write_to_file("q\\u{0}zzz", "x")))
    print(exists("q"))
    print(unit(write_to_file("q", "kept")))
    print(match read_to_string("q\\u{0}other") {
        Ok(s) => s,
        Err(e) => cause(e),
    })
    print(unit(make_dir("d\\u{0}")))
    print(unit(remove_file("q\\u{0}")))
    print(unit(rename("q", "r\\u{0}s")))
    print(unit(rename("q\\u{0}", "r")))
    print(unit(remove_dir("q\\u{0}")))
    print(exists("q\\u{0}"))
    print(match list_dir(".\\u{0}") {
        Ok(names) => "listed",
        Err(e) => cause(e),
    })
    print(match read_to_string("q") {
        Ok(s) => s,
        Err(e) => cause(e),
    })
}
"""
NUL_PATHS_OUTPUT = ("invalid input\nfalse\nok\ninvalid input\ninvalid input\ninvalid input\ninvalid input\ninvalid input\n"
                    "invalid input\nfalse\ninvalid input\nkept\n")


def prepare_tree(work: str) -> None:
    """`tree/` with files, nested directories and a link to `outside/`."""
    os.makedirs(os.path.join(work, "tree", "sub", "deeper"))
    os.makedirs(os.path.join(work, "outside"))
    for rel in ("tree/one", "tree/sub/two", "tree/sub/deeper/three", "outside/keep"):
        with open(os.path.join(work, rel), "w") as fh:
            fh.write(rel)
    os.symlink(os.path.join(work, "outside"), os.path.join(work, "tree", "link"))
    os.symlink("nowhere", os.path.join(work, "tree", "sub", "dangling"))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class IoErrorCauses(unittest.TestCase):
    """Each portable cause of an `IoError` (D129, MYLA-190), made to happen
    for real, named the same by the interpreter and native code."""

    def test_the_causes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err, code = run_source_both_now(
                "from std.fs import IoError, make_dir, remove_file, remove_dir, write_to_file, read_to_string\n"
                "fun cause(r: Result<(), IoError>) -> str {\n"
                "    return match r {\n"
                '        Ok(()) => "ok",\n'
                '        Err(IoError.NotFound) => "not found",\n'
                '        Err(IoError.PermissionDenied) => "permission denied",\n'
                '        Err(IoError.AlreadyExists) => "already exists",\n'
                '        Err(IoError.NotADirectory) => "not a directory",\n'
                '        Err(IoError.IsADirectory) => "is a directory",\n'
                '        Err(IoError.NotEmpty) => "not empty",\n'
                '        Err(IoError.Interrupted) => "interrupted",\n'
                '        Err(IoError.Cancelled) => "cancelled",\n'
                '        Err(IoError.Unsupported) => "unsupported",\n'
                '        Err(IoError.BrokenPipe) => "broken pipe",\n'
                '        Err(IoError.InvalidInput) => "invalid input",\n'
                '        Err(IoError.Other(c)) => f"other {c}",\n'
                '        Err(_) => "a network cause",\n'
                "    }\n"
                "}\n"
                "fun main() {\n"
                f'    let d = "{tmp}/d"\n'
                "    print(cause(make_dir(d)))\n"
                "    print(cause(make_dir(d)))\n"
                "    print(cause(remove_file(d)))\n"
                '    print(cause(write_to_file(d + "/f", "x")))\n'
                "    print(cause(remove_dir(d)))\n"
                '    print(cause(make_dir(d + "/f/g")))\n'
                '    print(cause(make_dir(d + "/no/such")))\n'
                '    print(cause(remove_file(d + "/f")))\n'
                "    print(cause(remove_dir(d)))\n"
                "}\n",
            )
        self.assertEqual((out, err, code), ("ok\nalready exists\nis a directory\nok\nnot empty\nnot a directory\n"
                                            "not found\nok\nok\n", "", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class DirectoryParity(unittest.TestCase):
    """The same program, in a fresh working directory, prints the same in the
    self-hosted interpreter and the self-hosted native backend (MYLA-88)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.interp = selfhost_tool("interp_main")
        cls.gen = selfhost_tool("gen_main")
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def commands(self, name: str, source: str) -> dict[str, list[str]]:
        """The command that runs `source` in each implementation."""
        d = os.path.join(self.tmp.name, name)
        os.makedirs(d)
        path = os.path.join(d, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)
        asm = subprocess.run([self.gen, path, STDLIB_ROOT, *target_flags()],
                             capture_output=True, text=True, check=True)
        sh_native = os.path.join(d, "sh_native")
        with open(sh_native + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm.stdout)
        assemble(sh_native + ".s", sh_native)
        return {
            "self-hosted interpreter": [self.interp, path, STDLIB_ROOT],
            "self-hosted native": run_argv(sh_native, sh_native)[0],
        }

    def work_dir(self, name: str, impl: str) -> str:
        """The working directory `run_all` gives the implementation `impl`."""
        return os.path.join(self.tmp.name, name, impl.replace(" ", "-"))

    def run_all(self, name: str, source: str, prepare=None, wrap=None) -> dict[str, tuple[str, str, int]]:
        """Run `source` in each implementation, each in its own empty working
        directory (filled by `prepare(dir)` first; the command is `wrap(argv)`
        if given)."""
        results = {}
        for impl, argv in self.commands(name, source).items():
            work = self.work_dir(name, impl)
            os.makedirs(work)
            if prepare is not None:
                prepare(work)
            if wrap is not None:
                argv = wrap(argv)
            proc = subprocess.run(argv, cwd=work, capture_output=True, timeout=120)
            results[impl] = (proc.stdout.decode(), proc.stderr.decode(), proc.returncode)
        return results

    def test_tour(self) -> None:
        for impl, result in self.run_all("tour", FS_TOUR).items():
            with self.subTest(implementation=impl):
                self.assertEqual(result, (FS_TOUR_OUTPUT, "", 0))

    def test_current_dir(self) -> None:
        for impl, result in self.run_all("cwd", CWD_PROGRAM).items():
            with self.subTest(implementation=impl):
                work = os.path.realpath(self.work_dir("cwd", impl))
                self.assertEqual(result, (f"{work} true\n", "", 0))

    def test_current_dir_removed(self) -> None:
        # The program starts in a directory that was removed: getcwd fails
        # with ENOENT.
        def wrap(argv: list[str]) -> list[str]:
            return ["sh", "-c", 'mkdir gone && cd gone && rmdir ../gone && exec "$@"', "sh", *argv]

        for impl, result in self.run_all("cwd-removed", CWD_PROGRAM, wrap=wrap).items():
            with self.subTest(implementation=impl):
                self.assertEqual(result, ("not found\n", "", 0))

    def test_remove_and_rename(self) -> None:
        for impl, result in self.run_all("remove", REMOVE_TOUR, prepare_tree).items():
            with self.subTest(implementation=impl):
                self.assertEqual(result, (REMOVE_TOUR_OUTPUT, "", 0))

    def test_a_nul_byte_in_a_path(self) -> None:
        for impl, result in self.run_all("nul", NUL_PATHS).items():
            with self.subTest(implementation=impl):
                self.assertEqual(result, (NUL_PATHS_OUTPUT, "", 0))
                self.assertEqual(sorted(os.listdir(self.work_dir("nul", impl))), ["q"])

    def test_many_long_names(self) -> None:
        names = [f"{i:03d}" + "x" * (i - 3) if i >= 3 else "n" * i for i in range(1, 256)]
        names += [f"short-{i}" for i in range(400)]

        def prepare(work: str) -> None:
            os.makedirs(os.path.join(work, "big"))
            for n in names:
                open(os.path.join(work, "big", n), "w").close()

        ordered = sorted(names, key=str.encode)
        expected = (f"{len(names)} names, {sum(map(len, names))} bytes\n"
                    + "".join(n + "\n" for n in ordered))
        for impl, result in self.run_all("many", MANY, prepare).items():
            with self.subTest(implementation=impl):
                self.assertEqual(result, (expected, "", 0))


if __name__ == "__main__":
    unittest.main()
