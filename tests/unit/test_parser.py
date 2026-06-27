"""Unit tests for the Myla parser (docs/grammar.md §2)."""
import unittest

from myla import ast
from myla.errors import ParseError
from myla.lexer import tokenize
from myla.parser import parse


def parse_src(src: str) -> ast.Program:
    return parse(tokenize(src))


def parse_expr(src: str):
    """Parse a single expression by wrapping it in a function body."""
    prog = parse_src("fun f() {\n    " + src + "\n}\n")
    body = prog.decls[0].body
    stmt = body.statements[0]
    assert isinstance(stmt, ast.ExprStmt), stmt
    return stmt.expr


def parse_stmt(src: str):
    prog = parse_src("fun f() {\n    " + src + "\n}\n")
    return prog.decls[0].body.statements[0]


class TestExpressions(unittest.TestCase):
    def test_int_literal(self):
        self.assertEqual(parse_expr("42"), ast.IntLit(42, None))

    def test_int_literal_with_suffix(self):
        self.assertEqual(parse_expr("255u8"), ast.IntLit(255, "u8"))

    def test_string_and_bool(self):
        self.assertEqual(parse_expr('"hi"'), ast.StrLit("hi"))
        self.assertEqual(parse_expr("true"), ast.BoolLit(True))

    def test_name(self):
        self.assertEqual(parse_expr("foo"), ast.Name("foo"))

    def test_arithmetic_precedence(self):
        # 1 + 2 * 3  ==  1 + (2 * 3)
        self.assertEqual(
            parse_expr("1 + 2 * 3"),
            ast.Binary("+", ast.IntLit(1), ast.Binary("*", ast.IntLit(2), ast.IntLit(3))),
        )

    def test_left_associativity(self):
        # 1 - 2 - 3  ==  (1 - 2) - 3
        self.assertEqual(
            parse_expr("1 - 2 - 3"),
            ast.Binary("-", ast.Binary("-", ast.IntLit(1), ast.IntLit(2)), ast.IntLit(3)),
        )

    def test_parentheses_override(self):
        self.assertEqual(
            parse_expr("(1 + 2) * 3"),
            ast.Binary("*", ast.Binary("+", ast.IntLit(1), ast.IntLit(2)), ast.IntLit(3)),
        )

    def test_logical_and_comparison_precedence(self):
        # a < b && c == d  ==  (a < b) && (c == d)
        self.assertEqual(
            parse_expr("a < b && c == d"),
            ast.Binary(
                "&&",
                ast.Binary("<", ast.Name("a"), ast.Name("b")),
                ast.Binary("==", ast.Name("c"), ast.Name("d")),
            ),
        )

    def test_unary(self):
        self.assertEqual(parse_expr("-x"), ast.Unary("-", ast.Name("x")))
        self.assertEqual(parse_expr("!ok"), ast.Unary("!", ast.Name("ok")))

    def test_call(self):
        self.assertEqual(
            parse_expr("add(1, 2)"),
            ast.Call(ast.Name("add"), [ast.IntLit(1), ast.IntLit(2)]),
        )

    def test_call_no_args(self):
        self.assertEqual(parse_expr("f()"), ast.Call(ast.Name("f"), []))

    def test_field_access_chain(self):
        self.assertEqual(
            parse_expr("a.b.c"),
            ast.FieldAccess(ast.FieldAccess(ast.Name("a"), "b"), "c"),
        )

    def test_struct_literal(self):
        self.assertEqual(
            parse_expr("Point { x: 1, y: 2 }"),
            ast.StructLit("Point", [
                ast.FieldInit("x", ast.IntLit(1)),
                ast.FieldInit("y", ast.IntLit(2)),
            ]),
        )


class TestStatements(unittest.TestCase):
    def test_let_inferred(self):
        self.assertEqual(
            parse_stmt("let x = 5"),
            ast.VarDecl("let", "x", None, ast.IntLit(5)),
        )

    def test_var_typed(self):
        self.assertEqual(
            parse_stmt("var x: int = 5"),
            ast.VarDecl("var", "x", ast.TypeRef("int"), ast.IntLit(5)),
        )

    def test_assignment(self):
        self.assertEqual(
            parse_stmt("x = x + 1"),
            ast.Assign(ast.Name("x"), ast.Binary("+", ast.Name("x"), ast.IntLit(1))),
        )

    def test_field_assignment(self):
        self.assertEqual(
            parse_stmt("p.x = 10"),
            ast.Assign(ast.FieldAccess(ast.Name("p"), "x"), ast.IntLit(10)),
        )

    def test_assign_to_non_lvalue_is_error(self):
        with self.assertRaises(ParseError):
            parse_stmt("1 + 2 = 3")

    def test_while(self):
        stmt = parse_stmt("while i < 3 {\n        i = i + 1\n    }")
        self.assertIsInstance(stmt, ast.While)
        self.assertEqual(stmt.cond, ast.Binary("<", ast.Name("i"), ast.IntLit(3)))
        self.assertEqual(len(stmt.body.statements), 1)

    def test_for_range(self):
        stmt = parse_stmt("for i in 0..5 {\n        x = i\n    }")
        self.assertIsInstance(stmt, ast.For)
        self.assertEqual(stmt.var_name, "i")
        self.assertEqual(stmt.start, ast.IntLit(0))
        self.assertEqual(stmt.end, ast.IntLit(5))

    def test_return_value_and_bare(self):
        self.assertEqual(parse_stmt("return 1 + 2"),
                         ast.Return(ast.Binary("+", ast.IntLit(1), ast.IntLit(2))))
        self.assertEqual(parse_stmt("return"), ast.Return(None))

    def test_if_else(self):
        stmt = parse_stmt("if x { a = 1 } else { a = 2 }")
        self.assertIsInstance(stmt, ast.If)
        self.assertIsInstance(stmt.then, ast.Block)
        self.assertIsInstance(stmt.otherwise, ast.Block)

    def test_else_if_chain(self):
        stmt = parse_stmt("if a { x = 1 } else if b { x = 2 } else { x = 3 }")
        self.assertIsInstance(stmt, ast.If)
        self.assertIsInstance(stmt.otherwise, ast.If)
        self.assertIsInstance(stmt.otherwise.otherwise, ast.Block)

    def test_else_on_next_line(self):
        stmt = parse_stmt("if a {\n        x = 1\n    } else {\n        x = 2\n    }")
        self.assertIsInstance(stmt, ast.If)
        self.assertIsInstance(stmt.otherwise, ast.Block)

    def test_condition_does_not_parse_struct_literal(self):
        # `if Foo { ... }` -> condition is the name Foo, body is the block.
        stmt = parse_stmt("if foo { x = 1 }")
        self.assertEqual(stmt.cond, ast.Name("foo"))


class TestDeclarations(unittest.TestCase):
    def test_struct_decl(self):
        prog = parse_src("struct Point {\n    x: int,\n    y: int,\n}\n")
        decl = prog.decls[0]
        self.assertEqual(decl, ast.StructDecl("Point", [
            ast.Field("x", ast.TypeRef("int")),
            ast.Field("y", ast.TypeRef("int")),
        ]))

    def test_fun_decl(self):
        prog = parse_src("fun add(a: int, b: int) -> int {\n    return a + b\n}\n")
        decl = prog.decls[0]
        self.assertIsInstance(decl, ast.FunDecl)
        self.assertEqual(decl.name, "add")
        self.assertEqual([p.name for p in decl.params], ["a", "b"])
        self.assertEqual(decl.ret_type, ast.TypeRef("int"))

    def test_fun_no_return_type(self):
        prog = parse_src("fun main() {\n    return\n}\n")
        self.assertIsNone(prog.decls[0].ret_type)

    def test_typealias(self):
        prog = parse_src("typealias Byte = uint8\n")
        self.assertEqual(prog.decls[0], ast.TypeAliasDecl("Byte", ast.TypeRef("uint8")))

    def test_sized_type_param(self):
        prog = parse_src("fun f(b: uint8) -> uint8 {\n    return b\n}\n")
        self.assertEqual(prog.decls[0].params[0].type, ast.TypeRef("uint8"))


class TestAttributes(unittest.TestCase):
    def test_main_attribute(self):
        prog = parse_src("#main\nfun run() {\n    return\n}\n")
        decl = prog.decls[0]
        self.assertEqual(len(decl.attributes), 1)
        self.assertEqual(decl.attributes[0], ast.Attribute("main", [], None))

    def test_test_attributes_stack(self):
        prog = parse_src("#test(1, 2)[3]\n#test(4, 2)[6]\nfun add(a: int, b: int) -> int {\n    return a + b\n}\n")
        attrs = prog.decls[0].attributes
        self.assertEqual(len(attrs), 2)
        self.assertEqual(attrs[0], ast.Attribute("test", [ast.IntLit(1), ast.IntLit(2)], [ast.IntLit(3)]))
        self.assertEqual(attrs[1], ast.Attribute("test", [ast.IntLit(4), ast.IntLit(2)], [ast.IntLit(6)]))


class TestErrors(unittest.TestCase):
    def test_missing_closing_brace(self):
        with self.assertRaises(ParseError):
            parse_src("fun f() {\n    return 1\n")

    def test_two_statements_one_line(self):
        with self.assertRaises(ParseError):
            parse_src("fun f() {\n    let a = 1 let b = 2\n}\n")

    def test_top_level_expression_is_error(self):
        with self.assertRaises(ParseError):
            parse_src("1 + 2\n")


if __name__ == "__main__":
    unittest.main()
