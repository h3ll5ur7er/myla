"""Unit tests for import-statement parsing and `pub` visibility (v0.5.1a).

The module loader (v0.5.1b) is tested separately; these cover the front end:
tokens, AST shape, and the D54 `pub import … as …` rule.
"""
import unittest

from myla import ast
from myla.errors import ParseError, TypeCheckError
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check


def parse_src(src: str) -> ast.Program:
    return parse(tokenize(src))


def first_import(src: str) -> ast.ImportDecl:
    decl = parse_src(src).decls[0]
    assert isinstance(decl, ast.ImportDecl), decl
    return decl


class TestImportParsing(unittest.TestCase):
    def test_whole_module_import(self):
        imp = first_import("import std.collections.list\n")
        self.assertEqual(imp.path.dots, 0)
        self.assertEqual(imp.path.segments, ["std", "collections", "list"])
        self.assertIsNone(imp.items)
        self.assertIsNone(imp.alias)
        self.assertFalse(imp.is_pub)

    def test_import_with_alias(self):
        imp = first_import("import std.collections.list as list\n")
        self.assertEqual(imp.path.segments, ["std", "collections", "list"])
        self.assertEqual(imp.alias, "list")

    def test_relative_single_dot(self):
        imp = first_import("from .utils import helper\n")
        self.assertEqual(imp.path.dots, 1)
        self.assertEqual(imp.path.segments, ["utils"])
        self.assertIsNotNone(imp.items)
        self.assertEqual([i.name for i in imp.items], ["helper"])

    def test_relative_parent_double_dot(self):
        imp = first_import("from ..shared import Token\n")
        self.assertEqual(imp.path.dots, 2)
        self.assertEqual(imp.path.segments, ["shared"])

    def test_relative_triple_dot(self):
        # `...` lexes as DOTDOT + DOT -> 3 levels up.
        imp = first_import("from ...root import x\n")
        self.assertEqual(imp.path.dots, 3)
        self.assertEqual(imp.path.segments, ["root"])

    def test_from_import_multiple_items_with_alias(self):
        imp = first_import("from .m import a, b as c, d\n")
        self.assertEqual(
            [(i.name, i.alias) for i in imp.items],
            [("a", None), ("b", "c"), ("d", None)],
        )

    def test_pub_import_with_alias(self):
        imp = first_import("pub import std.collections.list as list\n")
        self.assertTrue(imp.is_pub)
        self.assertEqual(imp.alias, "list")

    def test_pub_from_import(self):
        imp = first_import("pub from .utils import helper\n")
        self.assertTrue(imp.is_pub)
        self.assertEqual([i.name for i in imp.items], ["helper"])

    def test_dotted_path_round_trips(self):
        self.assertEqual(first_import("import a.b.c\n").path.dotted(), "a.b.c")
        self.assertEqual(first_import("from ..x.y import z\n").path.dotted(), "..x.y")


class TestPubVisibility(unittest.TestCase):
    def test_pub_on_struct_fun_enum(self):
        prog = parse_src(
            "pub struct P { x: int32 }\n"
            "pub fun f() {}\n"
            "pub enum E { A }\n"
            "struct Q { y: int32 }\n"
        )
        kinds = {d.name: d.is_pub for d in prog.decls}
        self.assertEqual(kinds, {"P": True, "f": True, "E": True, "Q": False})

    def test_pub_on_const_and_typealias(self):
        prog = parse_src(
            "pub const N: int32 = 1\n"
            "pub typealias Word = uint32\n"
        )
        self.assertTrue(all(d.is_pub for d in prog.decls))

    def test_pub_on_trait(self):
        prog = parse_src("pub trait Show { fun show(self) -> str }\n")
        self.assertTrue(prog.decls[0].is_pub)


class TestImportErrors(unittest.TestCase):
    def test_pub_import_requires_alias(self):
        with self.assertRaises(ParseError) as cm:
            parse_src("pub import std.collections.list\n")
        self.assertIn("as <name>", str(cm.exception))

    def test_pub_on_impl_rejected(self):
        with self.assertRaises(ParseError) as cm:
            parse_src("struct P {}\npub impl P { fun f(self) {} }\n")
        self.assertIn("impl", str(cm.exception))

    def test_attributes_on_import_rejected(self):
        with self.assertRaises(ParseError):
            parse_src("#main\nimport a.b\n")

    def test_missing_import_keyword_in_from(self):
        with self.assertRaises(ParseError):
            parse_src("from .utils helper\n")

    def test_empty_path_is_error(self):
        with self.assertRaises(ParseError):
            parse_src("import\n")


class TestCheckerGuard(unittest.TestCase):
    def test_import_rejected_without_the_loader(self):
        # the loader resolves imports; checking such a file on its own can't
        with self.assertRaises(TypeCheckError) as cm:
            check(parse_src("import a.b\nfun main() {}\n"))
        self.assertIn("imports need the module loader", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
