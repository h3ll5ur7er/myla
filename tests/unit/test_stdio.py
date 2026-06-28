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


def link_and_run(src: str, argv=None) -> tuple[str, str, int]:
    """Write `src` to a temp module, link it against the bundled stdlib, then run
    it through the interpreter; return (stdout, stderr, exit code). `argv` is the
    program command line seen by `std.process.args`."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        checker = check(link(path, stdlib_root=default_stdlib_root()))
        out, err = io.StringIO(), io.StringIO()
        code = Interpreter(checker, out, err, argv=argv).run()
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
