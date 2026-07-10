"""Unit tests for the subprocess runtime (v0.5.4 follow-on, D29).

Two layers are exercised:
  * the low-level `__run`/`__run_*` runtime primitives, as seen by the type
    checker (global builtins, so they need no import); and
  * the public `std.process` surface (`run`, `command`/`Command`, `Output`,
    `ExitStatus`, `SpawnError`), linked against the bundled standard library and
    executed by the interpreter.
"""
import io
import os
import tempfile
import unittest

from myla import ast
from myla.errors import TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.loader import default_stdlib_root, link
from myla.parser import parse
from myla.types import IntType, ListType, check


def check_src(src: str):
    return check(parse(tokenize(src)))


def link_and_run(src: str, argv=None) -> tuple[str, str, int]:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        checker = check(link(path, stdlib_root=default_stdlib_root()))
        out, err = io.StringIO(), io.StringIO()
        code = Interpreter(checker, out, err, argv=argv).run()
        return out.getvalue(), err.getvalue(), code


class TestRunPrimitives(unittest.TestCase):
    def test_run_accepts_program_and_argv(self):
        check_src('fun main() { let o = __run("/bin/echo", ["/bin/echo"]) }\n')

    def test_run_returns_byte_list(self):
        checker = check_src('fun main() { let o = __run("/bin/echo", ["x"]) }\n')
        main = next(d for d in checker.program.decls
                    if isinstance(d, ast.FunDecl) and d.name == "main")
        init = main.body.statements[0].init
        self.assertIsInstance(init.resolved_type, ListType)
        self.assertEqual(init.resolved_type.elem, IntType(8, False))

    def test_run_stderr_returns_byte_list(self):
        checker = check_src("fun main() { let e = __run_stderr() }\n")
        main = next(d for d in checker.program.decls
                    if isinstance(d, ast.FunDecl) and d.name == "main")
        init = main.body.statements[0].init
        self.assertIsInstance(init.resolved_type, ListType)
        self.assertEqual(init.resolved_type.elem, IntType(8, False))

    def test_run_scalars_return_int(self):
        for name in ("__run_exit_code", "__run_signal", "__run_errno"):
            checker = check_src(f"fun main() {{ let v = {name}() }}\n")
            main = next(d for d in checker.program.decls
                        if isinstance(d, ast.FunDecl) and d.name == "main")
            init = main.body.statements[0].init
            self.assertEqual(init.resolved_type, IntType(32, True), name)

    def test_run_rejects_wrong_arity(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { let o = __run("/bin/echo") }\n')

    def test_run_rejects_non_string_program(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { let o = __run(1, ["x"]) }\n')

    def test_run_rejects_non_string_argv(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { let o = __run("/bin/echo", [1]) }\n')

    def test_run_stderr_rejects_arguments(self):
        with self.assertRaises(TypeCheckError):
            check_src('fun main() { let e = __run_stderr("x") }\n')

    def test_run_errno_rejects_arguments(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun main() { let e = __run_errno(1) }\n")


class TestProcessStdlib(unittest.TestCase):
    def test_run_captures_stdout(self):
        out, err, code = link_and_run(
            "from std.io import write\n"
            "from std.process import run\n"
            "fun decode(bytes: [uint8]) -> str {\n"
            "    var sb = StringBuilder()\n"
            "    for b in bytes { append_byte(sb, b) }\n"
            "    return build(sb)\n"
            "}\n"
            "fun main() {\n"
            "    match run(\"/bin/echo\", [\"hello\"]) {\n"
            "        Ok(o) => write(1, decode(o.stdout)),\n"
            "        Err(e) => write(2, \"fail\"),\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("hello\n", "", 0))

    def test_run_reports_not_found(self):
        out, err, code = link_and_run(
            "from std.io import println\n"
            "from std.process import run, SpawnError\n"
            "fun describe(e: SpawnError) -> str {\n"
            "    return match e {\n"
            "        SpawnError.NotFound => \"notfound\",\n"
            "        SpawnError.PermissionDenied => \"perm\",\n"
            "        SpawnError.Other(code) => \"other\",\n"
            "    }\n"
            "}\n"
            "fun main() {\n"
            "    match run(\"/no/such/program\", []) {\n"
            "        Ok(o) => println(\"unexpected\"),\n"
            "        Err(e) => println(describe(e)),\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("notfound\n", "", 0))

    def test_command_builder(self):
        out, err, code = link_and_run(
            "from std.io import write\n"
            "from std.process import command\n"
            "fun decode(bytes: [uint8]) -> str {\n"
            "    var sb = StringBuilder()\n"
            "    for b in bytes { append_byte(sb, b) }\n"
            "    return build(sb)\n"
            "}\n"
            "fun main() {\n"
            "    match command(\"/bin/echo\").arg(\"x\").arg(\"y\").output() {\n"
            "        Ok(o) => write(1, decode(o.stdout)),\n"
            "        Err(e) => write(2, \"fail\"),\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual((out, err, code), ("x y\n", "", 0))


if __name__ == "__main__":
    unittest.main()
