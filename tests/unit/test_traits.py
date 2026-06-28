"""Unit tests for traits, operator overloading & derivable Eq (v0.4.4: D52/D53,
X8/X9).

Covers the front-end shape (parser: `trait`, `impl Trait for T`, bounds), the
checker (trait registry, conformance/coherence, operator desugaring, `#derive`,
generic bounds), and interpreter behavior (operator dispatch, derived equality,
bounded generics). Native parity lives in the burn suite.
"""
import io
import unittest

from myla import ast
from myla.errors import ParseError, TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check

_VEC = (
    "struct Vec2 { x: int, y: int }\n"
    "impl Add for Vec2 {\n"
    "    fun add(self, other: Vec2) -> Vec2 {\n"
    "        return Vec2 { x: self.x + other.x, y: self.y + other.y }\n"
    "    }\n"
    "}\n"
)


def run_src(src: str) -> str:
    out = io.StringIO()
    Interpreter(check(parse(tokenize(src))), out).run()
    return out.getvalue()


class TestParser(unittest.TestCase):
    def test_trait_decl_shape(self):
        prog = parse(tokenize(
            "trait Show {\n"
            "    fun show(self) -> str\n"
            "    fun loud(var self) -> str\n"
            "}\n"
        ))
        traits = [d for d in prog.decls if isinstance(d, ast.TraitDecl)]
        self.assertEqual(len(traits), 1)
        self.assertEqual([m.name for m in traits[0].methods], ["show", "loud"])
        # a trait method is a *signature*: no body.
        self.assertIsNone(traits[0].methods[0].body)
        self.assertEqual(traits[0].methods[1].receiver, "var self")

    def test_impl_for_clause(self):
        prog = parse(tokenize(_VEC))
        impl = [d for d in prog.decls if isinstance(d, ast.ImplDecl)][0]
        self.assertEqual(impl.trait_name, "Add")
        self.assertEqual(impl.target.name, "Vec2")

    def test_inherent_impl_has_no_trait_name(self):
        prog = parse(tokenize(
            "struct P { x: int }\nimpl P { fun g(self) -> int { return self.x } }\n"
        ))
        impl = [d for d in prog.decls if isinstance(d, ast.ImplDecl)][0]
        self.assertIsNone(impl.trait_name)

    def test_bounds_parsed(self):
        prog = parse(tokenize(
            "fun f<T: Add + Eq, U>(a: T, b: U) -> T { return a }\nfun main() {}\n"
        ))
        fn = [d for d in prog.decls if isinstance(d, ast.FunDecl)
              and d.name == "f"][0]
        self.assertEqual(fn.type_params, ["T", "U"])
        self.assertEqual(fn.type_param_bounds, {"T": ["Add", "Eq"]})

    def test_bounds_rejected_on_struct(self):
        with self.assertRaises(ParseError):
            parse(tokenize("struct S<T: Add> { v: T }\nfun main() {}\n"))


class TestChecker(unittest.TestCase):
    def test_trait_registered_and_impl_in_method_table(self):
        c = check(parse(tokenize(_VEC + "fun main() {}\n")))
        self.assertIn("Add", c.traits)
        self.assertIn("Add", c.trait_impls.get("Vec2", set()))
        self.assertIn("add", c.methods["Vec2"])

    def test_missing_method_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "trait T { fun a(self) -> int\n fun b(self) -> int }\n"
                "struct S {}\n"
                "impl T for S { fun a(self) -> int { return 1 } }\n"
                "fun main() {}\n"
            )))

    def test_signature_mismatch_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "trait T { fun a(self, x: int) -> int }\n"
                "struct S {}\n"
                "impl T for S { fun a(self, x: str) -> int { return 1 } }\n"
                "fun main() {}\n"
            )))

    def test_duplicate_trait_impl_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "trait T { fun a(self) -> int }\nstruct S {}\n"
                "impl T for S { fun a(self) -> int { return 1 } }\n"
                "impl T for S { fun a(self) -> int { return 2 } }\n"
                "fun main() {}\n"
            )))

    def test_operator_desugars_to_method_call(self):
        c = check(parse(tokenize(_VEC + "fun main() { let v = Vec2{x:1,y:2} + Vec2{x:3,y:4} }\n")))
        main = c.functions["main"].decl
        # `let v = …` initializer is now a `Vec2.add(...)` method call.
        init = main.body.statements[0].init
        self.assertIsInstance(init, ast.Call)
        self.assertEqual(getattr(init, "method_func", None), "Vec2.add")

    def test_operator_without_impl_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "struct P { x: int }\nfun main() { let b = P{x:1} == P{x:2} }\n"
            )))

    def test_primitive_operators_unchanged(self):
        # primitives keep their built-in operators (no desugaring, no impl needed)
        self.assertEqual(run_src("fun main() { print(1 + 2)\n print(3 == 3) }\n"),
                         "3\ntrue\n")

    def test_redeclare_builtin_trait_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "trait Add { fun add(self) -> int }\nfun main() {}\n"
            )))

    def test_derive_non_eq_field_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "struct Bare { x: int }\n#derive(Eq)\nstruct H { b: Bare }\n"
                "fun main() {}\n"
            )))

    def test_derive_unknown_trait_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize("#derive(Ord)\nstruct P { x: int }\nfun main() {}\n")))

    def test_bound_unsatisfied_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "struct P { x: int }\nfun twice<T: Add>(v: T) -> T { return v + v }\n"
                "fun main() { let p = twice(P{x:1}) }\n"
            )))

    def test_unbounded_operator_on_type_param_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "fun twice<T>(v: T) -> T { return v + v }\nfun main() {}\n"
            )))


class TestInterpreter(unittest.TestCase):
    def test_user_trait_method(self):
        src = (
            "trait Show { fun show(self) -> str }\n"
            "struct P { x: int }\n"
            "impl Show for P { fun show(self) -> str { return \"p\" } }\n"
            "fun main() { print(P{x:1}.show()) }\n"
        )
        self.assertEqual(run_src(src), "p\n")

    def test_operator_overloading(self):
        src = _VEC + (
            "fun main() {\n"
            "    let v = Vec2{x:1,y:2} + Vec2{x:3,y:4}\n"
            "    print(v.x)\n print(v.y)\n"
            "}\n"
        )
        self.assertEqual(run_src(src), "4\n6\n")

    def test_derived_eq_struct_and_enum(self):
        src = (
            "#derive(Eq)\nstruct Pt { x: int, y: int }\n"
            "#derive(Eq)\nenum E { A, B(int) }\n"
            "fun main() {\n"
            "    print(Pt{x:1,y:2} == Pt{x:1,y:2})\n"
            "    print(Pt{x:1,y:2} != Pt{x:9,y:2})\n"
            "    print(E.B(3) == E.B(3))\n"
            "    print(E.B(3) == E.A)\n"
            "}\n"
        )
        self.assertEqual(run_src(src), "true\ntrue\ntrue\nfalse\n")

    def test_ordering_overload(self):
        src = (
            "struct W { n: int }\n"
            "impl Ord for W { fun cmp(self, o: W) -> int { return self.n - o.n } }\n"
            "fun main() { print(W{n:1} < W{n:2})\n print(W{n:5} >= W{n:2}) }\n"
        )
        self.assertEqual(run_src(src), "true\ntrue\n")

    def test_generic_bound_over_primitive_and_user_type(self):
        src = _VEC + (
            "fun sum<T: Add>(xs: [T], zero: T) -> T {\n"
            "    var acc = zero\n for x in xs { acc = acc + x }\n return acc\n}\n"
            "fun main() {\n"
            "    print(sum([1, 2, 3], 0))\n"
            "    let v = sum([Vec2{x:1,y:1}, Vec2{x:2,y:2}], Vec2{x:0,y:0})\n"
            "    print(v.x)\n"
            "}\n"
        )
        self.assertEqual(run_src(src), "6\n3\n")


if __name__ == "__main__":
    unittest.main()
