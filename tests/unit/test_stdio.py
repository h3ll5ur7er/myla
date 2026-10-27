"""Unit tests for the freestanding I/O runtime (v0.5.4, D29).

Two layers are exercised:
  * the low-level `__write`/`__exit` runtime primitives, as seen by the type
    checker (these are global builtins, so they need no import); and
  * the public `std.io` / `std.process` surface, linked against the bundled
    standard library and executed by the interpreter.
"""
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


def link_and_run(src: str, argv=None, stdin: bytes | None = None) -> tuple[str, str, int]:
    """Write `src` to a temp module, link it against the bundled stdlib, then run
    it through the interpreter; return (stdout, stderr, exit code). `argv` is the
    program command line seen by `std.process.args`, `stdin` its input."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        checker = check(link(path, stdlib_root=default_stdlib_root()))
        out, err = io.StringIO(), io.StringIO()
        inp = io.BytesIO(stdin) if stdin is not None else None
        code = Interpreter(checker, out, err, argv=argv, stdin=inp).run()
        return out.getvalue(), err.getvalue(), code


class TestRuntimePrimitives(unittest.TestCase):
    def test_write_accepts_fd_and_string(self):
        check_src('fun main() { __write(1, "hi") }\n')

    def test_exit_accepts_integer(self):
        check_src("fun main() { __exit(0) }\n")

    def test_write_rejects_wrong_arity(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { __write("hi") }\n')

    def test_write_rejects_non_string_payload(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun main() { __write(1, 42) }\n")

    def test_write_rejects_non_integer_fd(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { __write("stdout", "hi") }\n')

    def test_exit_rejects_non_integer(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { __exit("nope") }\n')

    def test_args_returns_string_list(self):
        from myla import ast
        from myla.types import ListType, StrType
        checker = check_src("fun main() { let a = __args() }\n")
        main = next(d for d in checker.program.decls
                    if isinstance(d, ast.FunDecl) and d.name == "main")
        init = main.body.statements[0].init
        self.assertIsInstance(init.resolved_type, ListType)
        self.assertIsInstance(init.resolved_type.elem, StrType)

    def test_args_rejects_arguments(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { let a = __args("x") }\n')

    def test_exit_diverges_satisfying_return(self):
        # __exit never returns, so a value-returning function whose body ends in
        # __exit type-checks without a trailing `return` (it is diverging).
        check_src("fun f() -> int32 { __exit(1) }\nfun main() { let _ = f() }\n")

    def test_cannot_redefine_runtime_primitive(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun __write() {}\nfun main() {}\n")


class TestStdSurface(unittest.TestCase):
    def test_println_goes_to_stdout(self):
        out, err, code = link_and_run(
            "from std.io import println\n"
            'fun main() { println("hello") }\n'
        )
        self.assertEqual(out, "hello\n")
        self.assertEqual(err, "")
        self.assertEqual(code, 0)

    def test_eprint_and_eprintln_go_to_stderr(self):
        out, err, code = link_and_run(
            "from std.io import eprint, eprintln\n"
            'fun main() {\n    eprint("a")\n    eprintln("b")\n}\n'
        )
        self.assertEqual(out, "")
        self.assertEqual(err, "ab\n")

    def test_write_chooses_fd(self):
        out, err, _ = link_and_run(
            "from std.io import write\n"
            'fun main() {\n    write(1, "o")\n    write(2, "e")\n}\n'
        )
        self.assertEqual((out, err), ("o", "e"))

    def test_exit_sets_status(self):
        out, err, code = link_and_run(
            "from std.process import exit\n"
            "fun main() { exit(5) }\n"
        )
        self.assertEqual(code, 5)

    def test_exit_status_is_low_byte(self):
        _, _, code = link_and_run(
            "from std.process import exit\n"
            "fun main() { exit(257) }\n"   # 257 & 0xFF == 1
        )
        self.assertEqual(code, 1)

    def test_args_returns_program_argv(self):
        out, _, _ = link_and_run(
            "from std.io import println\n"
            "from std.process import args\n"
            "fun main() {\n"
            "    for a in args() { println(a) }\n"
            "}\n",
            argv=["prog", "one", "two"],
        )
        self.assertEqual(out, "prog\none\ntwo\n")

    def test_args_length_is_argc(self):
        out, _, _ = link_and_run(
            "from std.process import args\n"
            "fun main() { print(len(args())) }\n",
            argv=["prog", "a", "b", "c"],
        )
        self.assertEqual(out, "4\n")

    def test_args_empty_when_none_passed(self):
        out, _, _ = link_and_run(
            "from std.process import args\n"
            "fun main() { print(len(args())) }\n",
        )
        self.assertEqual(out, "0\n")

    def test_module_qualified_access(self):
        out, _, _ = link_and_run(
            "import std.io as io\n"
            'fun main() { io.println("qualified") }\n'
        )
        self.assertEqual(out, "qualified\n")

    def test_std_root_cannot_be_shadowed(self):
        # A project `std/` directory is a reserved-root violation (D57 r4).
        from myla.errors import ModuleError
        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, "std"))
            main = os.path.join(tmp, "main.my")
            with open(main, "w", encoding="utf-8") as fh:
                fh.write("from std.io import println\nfun main() {}\n")
            with self.assertRaises(ModuleError):
                link(main, stdlib_root=default_stdlib_root())


if __name__ == "__main__":
    unittest.main()


# -- reading (MYLA-78) ---------------------------------------------------------

# Prints each line of stdin with its length, then the count.
LINES = """from std.io import stdin
fun main() {
    var r = stdin()
    var n = 0
    while true {
        match r.read_line() {
            Ok(Some(line)) => {
                n = n + 1
                print(format("{}: [{}] {}", n, line, len(line)))
            },
            Ok(None) => { break },
            Err(e) => {
                print("error")
                break
            },
        }
    }
    print(format("{} lines", n))
}
"""

# Reads messages framed by a Content-Length header, as the language server
# protocol does, through a struct that owns the reader.
FRAMED = """from std.io import stdin, Reader
from std.fs import IoError

struct Channel { input: Reader }

impl Channel {
    // The next message's body; None at the end of the input.
    fun next(var self) -> Result<Option<str>, IoError> {
        var length = -1
        while true {
            match self.input.read_line()? {
                Some(line) => {
                    if len(line) <= 1 { break }       // "" or "\\r"
                    length = digits_of(line)
                },
                None => { return Ok(None) },
            }
        }
        return self.input.read_exact(length)
    }
}

fun digits_of(s: str) -> int32 {
    var n = 0
    for c in chars(s) {
        if c >= '0' && c <= '9' { n = n * 10 + ((c as int32) - 48) }
    }
    return n
}

fun main() {
    var ch = Channel { input: stdin() }
    while true {
        match ch.next() {
            Ok(Some(body)) => { print(format("<{}>", body)) },
            Ok(None) => { break },
            Err(e) => {
                print("error")
                break
            },
        }
    }
}
"""


class TestReadPrimitive(unittest.TestCase):
    def test_read_takes_fd_and_count(self):
        check_src("fun main() { let s: str = __read(0, 10) }\n")

    def test_read_rejects_wrong_arity(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun main() { __read(0) }\n")

    def test_read_rejects_non_integer_fd(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { __read("0", 1) }\n')

    def test_read_rejects_non_integer_count(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { __read(0, "1") }\n')

    def test_read_returns_at_most_n_bytes_then_empty(self):
        out, _, _ = link_and_run(
            'fun main() {\n'
            '    print(__read(0, 3))\n'
            '    print(__read(0, 100))\n'
            '    print(len(__read(0, 100)))\n'
            '    print(__io_errno())\n'
            '}\n', stdin=b"abcdef")
        self.assertEqual(out, "abc\ndef\n0\n0\n")

    def test_read_from_a_bad_fd_sets_errno(self):
        out, _, _ = link_and_run(
            'fun main() {\n'
            '    print(len(__read(99, 10)))\n'
            '    print(__io_errno())\n'
            '}\n')
        self.assertEqual(out, "0\n9\n")      # EBADF


class TestReader(unittest.TestCase):
    def test_lines(self):
        out, _, code = link_and_run(LINES, stdin=b"one\ntwo\n\nthree\n")
        self.assertEqual(out, "1: [one] 3\n2: [two] 3\n3: [] 0\n4: [three] 5\n4 lines\n")
        self.assertEqual(code, 0)

    def test_last_line_without_newline(self):
        out, _, _ = link_and_run(LINES, stdin=b"a\nb")
        self.assertEqual(out, "1: [a] 1\n2: [b] 1\n2 lines\n")

    def test_empty_input(self):
        out, _, _ = link_and_run(LINES, stdin=b"")
        self.assertEqual(out, "0 lines\n")

    def test_carriage_return_is_kept(self):
        out, _, _ = link_and_run(LINES, stdin=b"a\r\n")
        self.assertEqual(out, "1: [a\r] 2\n1 lines\n")

    def test_lines_longer_than_a_chunk(self):
        long = b"x" * 10000
        out, _, _ = link_and_run(LINES, stdin=long + b"\n" + long)
        lines = out.splitlines()
        self.assertEqual(lines[-1], "2 lines")
        self.assertTrue(lines[0].endswith("] 10000"))
        self.assertTrue(lines[1].endswith("] 10000"))

    def test_utf8_split_across_chunks(self):
        # 4,095 bytes of "x" put the two bytes of "ö" into different chunks
        out, _, _ = link_and_run(
            'from std.io import stdin\n'
            'fun main() {\n'
            '    var r = stdin()\n'
            '    match r.read_line() {\n'
            '        Ok(Some(s)) => {\n'
            '            var last = \' \'\n'
            '            for c in chars(s) { last = c }\n'
            '            print(len(s))\n'
            '            print(last)\n'
            '        },\n'
            '        _ => { print("error") },\n'
            '    }\n'
            '}\n', stdin=b"x" * 4095 + "ö\n".encode())
        self.assertEqual(out, "4097\nö\n")

    def test_read_to_end(self):
        out, _, _ = link_and_run(
            'from std.io import stdin, write\n'
            'fun main() {\n'
            '    var r = stdin()\n'
            '    match r.read_line() {\n'
            '        Ok(Some(first)) => { print(first) },\n'
            '        _ => {},\n'
            '    }\n'
            '    match r.read_to_end() {\n'
            '        Ok(rest) => { print(len(rest)) },\n'
            '        Err(e) => { print("error") },\n'
            '    }\n'
            '    match r.read_to_end() {\n'
            '        Ok(rest) => { print(len(rest)) },\n'
            '        Err(e) => { print("error") },\n'
            '    }\n'
            '}\n', stdin=b"head\n" + b"y" * 20000)
        self.assertEqual(out, "head\n20000\n0\n")

    def test_framed_messages(self):
        data = b"Content-Length: 5\r\n\r\nhello" + b"Content-Length: 12\r\n\r\n{\"a\": [1,2]}"
        out, _, _ = link_and_run(FRAMED, stdin=data)
        self.assertEqual(out, '<hello>\n<{"a": [1,2]}>\n')

    def test_read_exact_at_a_premature_end(self):
        out, _, _ = link_and_run(FRAMED, stdin=b"Content-Length: 10\r\n\r\nshort")
        self.assertEqual(out, "")

    def test_errors_are_io_errors(self):
        out, _, _ = link_and_run(
            'from std.io import reader\n'
            'from std.fs import IoError\n'
            'fun main() {\n'
            '    var r = reader(99)\n'
            '    match r.read_line() {\n'
            '        Err(IoError.Other(code)) => { print(code) },\n'
            '        _ => { print("no error") },\n'
            '    }\n'
            '}\n')
        self.assertEqual(out, "9\n")

    def test_read_exact_of_nothing(self):
        out, _, _ = link_and_run(
            'from std.io import stdin\n'
            'fun main() {\n'
            '    var r = stdin()\n'
            '    match r.read_exact(2) { Ok(Some(s)) => { print(s) }, _ => {} }\n'
            '    match r.read_exact(-3) { Ok(Some(s)) => { print(len(s)) }, _ => {} }\n'
            '    match r.read_exact(0) { Ok(Some(s)) => { print(len(s)) }, _ => {} }\n'
            '    match r.read_exact(2) { Ok(Some(s)) => { print(s) }, _ => {} }\n'
            '}\n', stdin=b"abcd")
        self.assertEqual(out, "ab\n0\n0\ncd\n")


class TestPoll(unittest.TestCase):
    """`__poll(fd, timeout_ms)` and `Reader.ready` (MYLA-80)."""

    def test_poll_takes_fd_and_timeout(self):
        check_src("fun main() { let n: int32 = __poll(0, 10) }\n")

    def test_poll_rejects_wrong_arguments(self):
        for call in ["__poll(0)", '__poll("0", 1)', '__poll(0, "1")']:
            with self.subTest(call=call):
                with self.assertRaises(TypeCheckError):
                    check_src(f"fun main() {{ {call} }}\n")

    def test_a_stream_is_always_ready(self):
        out, _, _ = link_and_run(
            'from std.io import stdin\n'
            'fun main() {\n'
            '    print(__poll(0, 0))\n'
            '    var r = stdin()\n'
            '    print(r.ready(0))\n'
            '}\n', stdin=b"")
        self.assertEqual(out, "1\ntrue\n")

    def test_a_bad_fd(self):
        out, _, _ = link_and_run('fun main() {\n    print(__poll(99, 0))\n}\n')
        self.assertEqual(out, "1\n")      # poll(2) reports POLLNVAL: a read would not block

