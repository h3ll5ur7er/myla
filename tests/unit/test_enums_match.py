"""Unit tests for v0.2 enums and `match`: parsing, checking, interpretation."""
import io
import unittest

from myla import ast
from myla.errors import TypeCheckError
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


ENUM = "enum Shape { Circle(int), Rect(int, int), Empty }\n"


class TestEnumParsing(unittest.TestCase):
    def test_enum_decl(self):
        prog = parse_src(ENUM)
        decl = prog.decls[0]
        self.assertIsInstance(decl, ast.EnumDecl)
        self.assertEqual([v.name for v in decl.variants], ["Circle", "Rect", "Empty"])
        self.assertEqual(len(decl.variants[1].payload), 2)

    def test_match_arm_shapes(self):
        prog = parse_src(
            "enum C { A, B }\n"
            "fun f(c: C) -> int { return match c { A => 1, B => 2 } }\n"
        )
        m = prog.decls[1].body.statements[0].value
        self.assertIsInstance(m, ast.Match)
        self.assertEqual(len(m.arms), 2)


class TestEnumChecking(unittest.TestCase):
    def test_construct_and_match_ok(self):
        check_src(
            ENUM
            + "fun f(s: Shape) -> int {\n"
            + "    return match s { Shape.Circle(r) => r, Shape.Rect(w, h) => w + h, Shape.Empty => 0 }\n"
            + "}\n"
        )

    def test_unknown_variant(self):
        with self.assertRaises(TypeCheckError):
            check_src(ENUM + "fun f() -> Shape { return Shape.Oval(1) }\n")

    def test_wrong_payload_arity(self):
        with self.assertRaises(TypeCheckError):
            check_src(ENUM + "fun f() -> Shape { return Shape.Rect(1) }\n")

    def test_nonexhaustive(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                ENUM + "fun f(s: Shape) -> int {\n"
                "    return match s { Shape.Circle(r) => r, Shape.Empty => 0 }\n}\n"
            )

    def test_redundant_arm(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                "enum C { A, B }\n"
                "fun f(c: C) -> int {\n"
                "    return match c { _ => 0, A => 1 }\n}\n"
            )

    def test_payload_variant_needs_args_in_pattern(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                ENUM + "fun f(s: Shape) -> int {\n"
                "    return match s { Circle => 1, _ => 0 }\n}\n"
            )

    def test_or_pattern_binding_mismatch(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                "enum E { A(int), B(int) }\n"
                "fun f(e: E) -> int {\n"
                "    return match e { A(x) | B(y) => x, }\n}\n"
            )

    def test_arms_must_agree_in_type(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                ENUM + "fun f(s: Shape) {\n"
                "    let x = match s { Shape.Circle(r) => r, Shape.Rect(w, h) => true, Shape.Empty => 0 }\n}\n"
            )

    def test_recursive_enum_accepted_and_boxed(self):
        c = check_src("enum Expr { Num(int), Add(Expr, Expr) }\n")
        self.assertIn("Expr", c.recursive_enums)

    def test_non_recursive_enum_not_boxed(self):
        c = check_src(ENUM)
        self.assertNotIn("Shape", c.recursive_enums)

    def test_mutually_recursive_enums_boxed(self):
        c = check_src("enum A { Ax(B), Az }\nenum B { By(A), Bz }\n")
        self.assertEqual({"A", "B"}, c.recursive_enums)

    def test_recursive_struct_still_rejected(self):
        # structs/tuples have no place to insert indirection -> infinite size
        with self.assertRaises(TypeCheckError):
            check_src("struct Node {\n    value: int,\n    next: Node,\n}\n")

    def test_enum_holding_recursive_enum_not_itself_recursive(self):
        c = check_src("enum List { Cons(int, List), Nil }\n"
                      "enum Wrap { W(List), Empty }\n")
        self.assertIn("List", c.recursive_enums)
        self.assertNotIn("Wrap", c.recursive_enums)

    def test_guard_must_be_bool(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                ENUM + "fun f(s: Shape) -> int {\n"
                "    return match s { Shape.Circle(r) if r => r, _ => 0 }\n}\n"
            )


class TestEnumInterpreter(unittest.TestCase):
    def test_payload_and_guard(self):
        out = run_src(
            ENUM + "fun classify(s: Shape) -> str {\n"
            "    return match s {\n"
            "        Shape.Circle(r) if r > 10 => \"big\",\n"
            "        Shape.Circle(_) => \"small\",\n"
            "        _ => \"other\",\n"
            "    }\n}\n"
            "fun main() {\n"
            "    print(classify(Shape.Circle(20)))\n"
            "    print(classify(Shape.Circle(1)))\n"
            "    print(classify(Shape.Empty))\n}\n"
        )
        self.assertEqual(out, "big\nsmall\nother\n")

    def test_bare_variant_and_or(self):
        out = run_src(
            "enum Color { Red, Green, Blue }\n"
            "fun f(c: Color) -> str { return match c { Red => \"r\", Green | Blue => \"gb\" } }\n"
            "fun main() {\n    print(f(Color.Red))\n    print(f(Color.Blue))\n}\n"
        )
        self.assertEqual(out, "r\ngb\n")

    def test_match_returns_enum(self):
        out = run_src(
            "enum Opt { Some(int), None }\n"
            "fun bump(o: Opt) -> Opt { return match o { Opt.Some(n) => Opt.Some(n + 1), Opt.None => Opt.None } }\n"
            "fun get(o: Opt) -> int { return match o { Opt.Some(n) => n, Opt.None => -1 } }\n"
            "fun main() {\n    print(get(bump(Opt.Some(41))))\n    print(get(bump(Opt.None)))\n}\n"
        )
        self.assertEqual(out, "42\n-1\n")

    def test_recursive_list(self):
        out = run_src(
            "enum List { Cons(int, List), Nil }\n"
            "fun sum(xs: List) -> int {\n"
            "    return match xs { List.Cons(h, t) => h + sum(t), List.Nil => 0 }\n}\n"
            "fun main() {\n"
            "    print(sum(List.Cons(1, List.Cons(2, List.Cons(3, List.Nil)))))\n}\n"
        )
        self.assertEqual(out, "6\n")

    def test_recursive_tree_nested_patterns(self):
        out = run_src(
            "enum Tree { Leaf(int), Node(Tree, Tree) }\n"
            "fun total(t: Tree) -> int {\n"
            "    return match t { Tree.Leaf(n) => n, Tree.Node(l, r) => total(l) + total(r) }\n}\n"
            "fun main() {\n"
            "    print(total(Tree.Node(Tree.Node(Tree.Leaf(1), Tree.Leaf(2)), Tree.Leaf(7))))\n}\n"
        )
        self.assertEqual(out, "10\n")


if __name__ == "__main__":
    unittest.main()
