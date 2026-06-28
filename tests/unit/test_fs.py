"""Unit tests for the filesystem runtime (v0.5.4c, D29).

Covers the low-level `__read_file`/`__io_errno` primitives as the type checker
sees them, and the public `std.fs.read_to_string -> Result<str, IoError>`
surface run through the interpreter (real file IO, errno-keyed errors)."""
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


if __name__ == "__main__":
    unittest.main()
