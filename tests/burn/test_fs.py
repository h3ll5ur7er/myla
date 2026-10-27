"""Burn tests for the filesystem runtime (v0.5.4c, D29).

`std.fs.read_to_string` is exercised end-to-end: the committed `examples/readfile`
program (which also uses argv, the I/O streams, and exit) plus focused parity
programs are linked against the bundled stdlib and run through both the
interpreter and the native compiler, which must agree on stdout, stderr, and the
process exit status — including the errno-keyed `IoError` paths.

The directory functions (`list_dir`, `make_dir`, `make_dir_all`, `exists`,
`is_dir`, `is_file`; MYLA-88) are run in all four implementations: the Python
interpreter, the Python native backend, the self-hosted interpreter and the
self-hosted native backend, each in a fresh working directory."""
import os
import subprocess
import sys
import tempfile
import unittest

from myla.compiler import build
from myla.loader import default_stdlib_root

from ._native import (
    CAN_BUILD_NATIVE,
    SKIP_REASON,
    build_and_run_full,
    check_file,
    interpret_full,
    write_program,
)
from ._tools import selfhost_tool
from tests.unit.test_fs import FS_TOUR, FS_TOUR_OUTPUT

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

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


class TestReadFileExample(unittest.TestCase):
    def test_interpreter_echoes_file(self):
        out, err, code = interpret_full(check_file(EXAMPLE), argv=["prog", POEM])
        self.assertEqual(out, POEM_TEXT)
        self.assertEqual((err, code), ("", 0))

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_native_matches_interpreter(self):
        interp = interpret_full(check_file(EXAMPLE), argv=["prog", POEM])
        native = build_and_run_full(check_file(EXAMPLE), args=[POEM], argv0="prog")
        self.assertEqual(native, (POEM_TEXT, "", 0))
        self.assertEqual(interp, native)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_missing_file_parity(self):
        interp = interpret_full(check_file(EXAMPLE), argv=["prog", "/no/such/file"])
        native = build_and_run_full(
            check_file(EXAMPLE), args=["/no/such/file"], argv0="prog")
        self.assertEqual(native, ("", "no such file\n", 1))
        self.assertEqual(interp, native)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_missing_argument_parity(self):
        interp = interpret_full(check_file(EXAMPLE), argv=["prog"])
        native = build_and_run_full(check_file(EXAMPLE), args=[], argv0="prog")
        self.assertEqual(native, ("", "usage: readfile <path>\n", 2))
        self.assertEqual(interp, native)


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
            "        Ok(s) => print(len(s)),\n"
            "        Err(e) => print(-1),\n"
            "    }\n"
            "}\n",
        )
        self.assertEqual(out, f"{len(POEM_TEXT.encode('utf-8'))}\n")

    def test_not_found_errno_parity(self):
        out, _, _ = _run_both(
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
        out, err, code = _run_both(
            "from std.io import write\n"
            "from std.fs import write_to_file, read_to_string, IoError\n"
            "fun main() {\n"
            f'    match write_to_file("{path}", "abc\\nλ done\\n") {{\n'
            "        Ok(n) => print(n),\n"
            "        Err(e) => print(-1),\n"
            "    }\n"
            f'    match read_to_string("{path}") {{\n'
            "        Ok(s) => write(1, s),\n"
            '        Err(e) => write(2, "read-fail"),\n'
            "    }\n"
            "}\n",
        )
        # "abc\nλ done\n" is 12 bytes (λ = 2), then the verbatim file content.
        self.assertEqual((out, err, code), ("12\nabc\nλ done\n", "", 0))

    def test_write_to_missing_dir_errno_parity(self):
        out, _, _ = _run_both(
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
            '    match write_to_file("/no/such/dir/out.txt", "x") {\n'
            '        Ok(n) => println("?"),\n'
            "        Err(e) => println(describe(e)),\n"
            "    }\n"
            "}\n",
        )
        self.assertEqual(out, "not-found\n")


    def test_directory_read_is_other_errno(self):
        # Opening a directory succeeds but reading it fails with EISDIR (21),
        # which maps to IoError.Other — and both backends must agree on the code.
        out, _, _ = _run_both(
            "from std.fs import read_to_string, IoError\n"
            "fun code_of(e: IoError) -> int32 {\n"
            "    return match e {\n"
            "        IoError.Other(c) => c,\n"
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


# A directory with many entries of every length from 1 to 255 bytes (the
# longest name Linux allows), so getdents64 fills its buffer many times and
# the native result grows several times over.
MANY = """from std.fs import list_dir
from std.io import println
fun main() {
    match list_dir("big") {
        Ok(names) => {
            var total = 0
            for n in names { total = total + len(n) }
            println(format("{} names, {} bytes", len(names), total))
            for n in names { println(n) }
        },
        Err(e) => { println("error") },
    }
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class DirectoryParity(unittest.TestCase):
    """The same program, in a fresh working directory, prints the same in the
    Python interpreter, the Python native backend, the self-hosted interpreter
    and the self-hosted native backend (MYLA-88)."""

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
        py_native = os.path.join(d, "py_native")
        build(check_file(path), py_native)
        asm = subprocess.run([self.gen, path, default_stdlib_root()],
                             capture_output=True, text=True, check=True)
        sh_native = os.path.join(d, "sh_native")
        with open(sh_native + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm.stdout)
        subprocess.run(["as", "--64", "-o", sh_native + ".o", sh_native + ".s"], check=True)
        subprocess.run(["ld", "-o", sh_native, sh_native + ".o"], check=True)
        return {
            "python interpreter": [sys.executable, os.path.join(_REPO, "myla.py"), "run", path],
            "python native": [py_native],
            "self-hosted interpreter": [self.interp, path, default_stdlib_root()],
            "self-hosted native": [sh_native],
        }

    def run_all(self, name: str, source: str, prepare=None) -> dict[str, tuple[str, str, int]]:
        """Run `source` in each implementation, each in its own empty working
        directory (filled by `prepare(dir)` first)."""
        results = {}
        for impl, argv in self.commands(name, source).items():
            work = os.path.join(self.tmp.name, name, impl.replace(" ", "-"))
            os.makedirs(work)
            if prepare is not None:
                prepare(work)
            proc = subprocess.run(argv, cwd=work, capture_output=True, timeout=120)
            results[impl] = (proc.stdout.decode(), proc.stderr.decode(), proc.returncode)
        return results

    def test_tour(self) -> None:
        for impl, result in self.run_all("tour", FS_TOUR).items():
            with self.subTest(implementation=impl):
                self.assertEqual(result, (FS_TOUR_OUTPUT, "", 0))

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
