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

    def test_arm_block_of_a_statement_match_may_end_in_a_match(self):
        # MYLA-59: the inner match is a statement, like the outer one
        src = ("fun main() {\n    let r: Result<int, str> = Ok(1)\n    match r {\n"
               "        Ok(n) => {\n            print(n)\n            match n {\n"
               "                1 => print(\"one\")\n                _ => print(\"other\")\n"
               "            }\n        }\n        Err(e) => print(e)\n    }\n}\n")
        self.assertEqual(run_src(src), "1\none\n")

    def test_a_value_match_still_needs_values(self):
        with self.assertRaises(TypeCheckError) as cm:
            check_src("fun main() {\n    let v = match 1 {\n        1 => {\n"
                      "            match 2 {\n                _ => print(1)\n            }\n"
                      "        }\n        _ => 0\n    }\n}\n")
        self.assertEqual(cm.exception.message,
                         "this match is used as a value, so every arm must produce one")

    def test_literal_patterns_must_fit_the_scrutinee(self):
        # a pattern is compared as written, so -1 on uint8 or 128 on int8 can
        # never match (MYLA-7)
        def match_on(t: str, pattern: str) -> str:
            return (f"fun f(x: {t}) -> int {{\n"
                    f"    return match x {{ {pattern} => 1, _ => 0 }}\n}}\n")
        for t, pattern, shown in (("uint8", "-1", "-1"), ("int8", "128", "128"),
                                  ("int8", "-129", "129"), ("uint64", "-1u64", "-1"),
                                  ("int64", "9223372036854775808", "9223372036854775808")):
            with self.subTest(t=t, pattern=pattern):
                with self.assertRaises(TypeCheckError) as cm:
                    check_src(match_on(t, pattern))
                self.assertEqual(cm.exception.message,
                                 f"integer literal {shown} does not fit in '{t}'")
        for t, pattern in (("int8", "-128"), ("int8", "127"), ("uint8", "255"), ("uint8", "-0"),
                           ("int64", "-9223372036854775808"), ("uint64", "18446744073709551615"),
                           ("uint8", "'a'")):
            with self.subTest(t=t, pattern=pattern):
                check_src(match_on(t, pattern))


class TestExhaustiveness(unittest.TestCase):
    """MYLA-14: exhaustiveness and redundancy by pattern matrices (Maranget's
    usefulness), so nested patterns, or-patterns, tuples and structs count."""

    def matches(self, scrutinee_type: str, arms: list[str], before: str = "") -> None:
        body = "".join(f"        {a} => 0,\n" for a in arms)
        check_src(f"{before}fun f(x: {scrutinee_type}) -> int {{\n"
                  f"    return match x {{\n{body}    }}\n}}\n")

    def rejected(self, scrutinee_type: str, arms: list[str], before: str = "") -> str:
        with self.assertRaises(TypeCheckError) as cm:
            self.matches(scrutinee_type, arms, before)
        return cm.exception.message

    def test_exhaustive(self):
        P = "struct P { a: bool, b: int }\n"
        for t, arms, before in (
            ("bool", ["true | false"], ""),
            ("Option<Result<int, str>>", ["Some(Ok(v))", "Some(Err(e))", "None"], ""),
            ("(bool, bool)", ["(true, _)", "(false, true)", "(false, false)"], ""),
            ("P", ["P { a: true }", "P { a: false, b: 1 }", "P { a: false }"], P),
            ("Option<bool>", ["Some(true) | None", "Some(false)"], ""),
            ("(Option<int>, bool)", ["(None, _)", "(Some(n), true)", "(_, false)"], ""),
        ):
            with self.subTest(t=t, arms=arms):
                self.matches(t, arms, before)

    def test_non_exhaustive(self):
        for t, arms, message in (
            ("Option<Result<int, str>>", ["Some(Ok(v))", "None"],
             "non-exhaustive match on 'Option': missing variant(s) Some (add them or a '_' arm)"),
            ("(bool, bool)", ["(true, _)", "(false, true)"],
             "non-exhaustive match on '(bool, bool)': add a '_' arm"),
            ("bool", ["true"],
             "non-exhaustive match on 'bool': cover both true and false (or add a '_' arm)"),
            ("Option<bool>", ["Some(true)", "None"],
             "non-exhaustive match on 'Option': missing variant(s) Some (add them or a '_' arm)"),
            ("int", ["1", "2"], "non-exhaustive match on 'int32': add a '_' arm"),
        ):
            with self.subTest(t=t, arms=arms):
                self.assertEqual(self.rejected(t, arms), message)

    def test_a_guarded_arm_does_not_cover(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f(x: bool) -> int {\n    return match x {\n"
                      "        true => 1,\n        false if 1 > 0 => 2,\n    }\n}\n")

    def test_redundant(self):
        for t, arms, message in (
            ("Option<Result<int, str>>", ["Some(Ok(v))", "Some(Ok(1))", "_"],
             "unreachable match arm (earlier arms already cover it)"),
            ("int", ["1", "1", "_"], "unreachable match arm (earlier arms already cover it)"),
            ("(bool, bool)", ["(true, _)", "(_, true)", "(true, false)", "_"],
             "unreachable match arm (earlier arms already cover it)"),
            ("bool", ["true", "false", "_"],
             "unreachable match arm (earlier arms already cover it)"),
            ("Option<int>", ["None", "Some(n)", "None"],
             "unreachable match arm (its variant(s) are already covered)"),
            ("int", ["n", "2"],
             "unreachable match arm (a previous arm already matches everything)"),
        ):
            with self.subTest(t=t, arms=arms):
                self.assertEqual(self.rejected(t, arms), message)


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
            "fun peel(o: Opt) -> int { return match o { Opt.Some(n) => n, Opt.None => -1 } }\n"
            "fun main() {\n    print(peel(bump(Opt.Some(41))))\n    print(peel(bump(Opt.None)))\n}\n"
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



class TestTryInLambdas(unittest.TestCase):
    """MYLA-72: `?` inside a lambda propagates out of the lambda, so it is
    checked against the lambda's result type, not the enclosing function's."""

    HALF = ("fun half(x: int) -> Option<int> {\n"
            "    if x % 2 == 1 { return None }\n    return Some(x / 2)\n}\n")

    def test_annotated_expression_lambda(self):
        src = self.HALF + (
            "fun main() {\n"
            "    let g: (int) -> Option<int> = (x: int) => Some(half(x)? + 100)\n"
            "    print(match g(4) { Some(v) => v, None => -1 })\n"
            "    print(match g(3) { Some(v) => v, None => -1 })\n}\n")
        self.assertEqual(run_src(src), "102\n-1\n")

    def test_expression_lambda_passed_as_an_argument(self):
        src = self.HALF + (
            "fun apply(f: (int) -> Option<int>, x: int) -> int {\n"
            "    return match f(x) { Some(v) => v, None => 0 }\n}\n"
            "fun main() {\n"
            "    print(apply((x) => Some(half(x)? * 10), 8))\n}\n")
        self.assertEqual(run_src(src), "40\n")

    def test_the_enclosing_function_type_no_longer_counts(self):
        # main returns an Option, but the lambda returns a Result
        src = self.HALF + (
            "fun main() -> Option<int> {\n"
            "    let g: (int) -> Result<int, str> = (x: int) => Ok(half(x)?)\n"
            "    return None\n}\n")
        with self.assertRaisesRegex(TypeCheckError, "lambda"):
            check_src(src)

    def test_a_lambda_of_unknown_result_type_says_so(self):
        src = self.HALF + (
            "fun main() {\n"
            "    let g = (x: int) => Some(half(x)? + 1)\n}\n")
        with self.assertRaisesRegex(TypeCheckError, "lambda's result type"):
            check_src(src)


if __name__ == "__main__":
    unittest.main()
