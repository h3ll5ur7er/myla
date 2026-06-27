"""Unit tests for v0.2 tuples: parsing, type-checking, and interpretation."""
import io
import unittest

from myla import ast
from myla.errors import ParseError, TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check


def parse_src(src: str) -> ast.Program:
    return parse(tokenize(src))


def check_src(src: str):
    return check(parse_src(src))


def run_src(src: str) -> str:
    checker = check_src(src)
    out = io.StringIO()
    Interpreter(checker, out).run()
    return out.getvalue()


class TestTupleParsing(unittest.TestCase):
    def test_tuple_literal_vs_grouping(self):
        prog = parse_src("fun f() {\n    let a = (1, 2)\n    let b = (3)\n}\n")
        body = prog.decls[0].body.statements
        self.assertIsInstance(body[0].init, ast.TupleLit)
        # a lone parenthesized expression is just grouping, not a 1-tuple
        self.assertIsInstance(body[1].init, ast.IntLit)

    def test_one_tuple_requires_trailing_comma(self):
        prog = parse_src("fun f() {\n    let a = (42,)\n}\n")
        lit = prog.decls[0].body.statements[0].init
        self.assertIsInstance(lit, ast.TupleLit)
        self.assertEqual(len(lit.elems), 1)

    def test_tuple_index(self):
        prog = parse_src("fun f() {\n    let a = (1, 2)\n    print(a.0)\n}\n")
        call = prog.decls[0].body.statements[1].expr
        self.assertIsInstance(call.args[0], ast.TupleIndex)
        self.assertEqual(call.args[0].index, 0)

    def test_tuple_index_rejects_suffix(self):
        with self.assertRaises(ParseError):
            parse_src("fun f() {\n    let a = (1, 2)\n    print(a.0u8)\n}\n")

    def test_destructuring_binding(self):
        prog = parse_src("fun f() {\n    let (a, _) = (1, 2)\n}\n")
        decl = prog.decls[0].body.statements[0]
        self.assertIsInstance(decl, ast.DestructDecl)
        self.assertIsInstance(decl.binding.elems[0], ast.BindName)
        self.assertIsInstance(decl.binding.elems[1], ast.BindWildcard)

    def test_multiple_return_is_tuple(self):
        prog = parse_src("fun f() -> (int, int) {\n    return 1, 2\n}\n")
        ret = prog.decls[0].body.statements[0]
        self.assertIsInstance(ret.value, ast.TupleLit)

    def test_one_tuple_type_needs_comma(self):
        with self.assertRaises(ParseError):
            parse_src("fun f(x: (int)) {\n}\n")


class TestTupleTypes(unittest.TestCase):
    def test_basic_ok(self):
        check_src(
            "fun f() -> (int, str) {\n    return 1, \"x\"\n}\n"
            "fun main() {\n    let (a, b) = f()\n    print(a)\n    print(b)\n}\n"
        )

    def test_index_out_of_range(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f() {\n    let a = (1, 2)\n    print(a.2)\n}\n")

    def test_index_on_non_tuple(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f() {\n    let a = 5\n    print(a.0)\n}\n")

    def test_destructure_arity_mismatch(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f() {\n    let (a, b, c) = (1, 2)\n}\n")

    def test_destructure_non_tuple(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f() {\n    let (a, b) = 5\n}\n")

    def test_annotation_mismatch(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f() {\n    let p: (int, str) = (1, 2)\n}\n")

    def test_tuple_equality_rejected(self):
        # `==` is primitives-only in v0.2 (D37)
        with self.assertRaises(TypeCheckError):
            check_src("fun f() {\n    let b = (1, 2) == (1, 2)\n}\n")

    def test_element_int_literal_inference(self):
        check_src("fun f() {\n    let p: (int64, int64) = (1, 2)\n}\n")


class TestTupleInterpreter(unittest.TestCase):
    def test_index_and_destructure(self):
        out = run_src(
            "fun main() {\n"
            "    let p = (1, 2)\n"
            "    print(p.0)\n"
            "    let (a, b) = p\n"
            "    print(a + b)\n"
            "}\n"
        )
        self.assertEqual(out, "1\n3\n")

    def test_nested_destructure(self):
        out = run_src(
            "fun main() {\n"
            "    let ((a, b), c) = ((10, 20), 30)\n"
            "    print(a + b + c)\n"
            "}\n"
        )
        self.assertEqual(out, "60\n")

    def test_value_semantics(self):
        # Destructuring a tuple of structs copies; mutating the copy is isolated.
        out = run_src(
            "struct P {\n    x: int,\n}\n"
            "fun main() {\n"
            "    let orig = P { x: 1 }\n"
            "    let t = (orig, 2)\n"
            "    var c = t.0\n"
            "    c.x = 99\n"
            "    print(orig.x)\n"
            "    print(c.x)\n"
            "}\n"
        )
        self.assertEqual(out, "1\n99\n")


if __name__ == "__main__":
    unittest.main()
