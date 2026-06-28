"""Unit tests for methods & `impl` blocks (v0.4.1: D45–D47).

Covers the front-end shape (parser), the checker's method table / coherence
rules / receiver mutability, and interpreter dispatch (incl. `var self`
write-back and value semantics). Native parity lives in the burn suite.
"""
import io
import unittest

from myla import ast
from myla.errors import ParseError, TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check

_POINT = (
    "struct Point { x: int, y: int }\n"
    "impl Point {\n"
    "    fun sum(self) -> int { return self.x + self.y }\n"
    "    fun shift(var self, d: int) { self.x = self.x + d }\n"
    "}\n"
)


def run_src(src: str) -> str:
    out = io.StringIO()
    Interpreter(check(parse(tokenize(src))), out).run()
    return out.getvalue()


class TestParser(unittest.TestCase):
    def test_impl_decl_shape(self):
        prog = parse(tokenize(_POINT))
        impls = [d for d in prog.decls if isinstance(d, ast.ImplDecl)]
        self.assertEqual(len(impls), 1)
        impl = impls[0]
        self.assertEqual([m.name for m in impl.methods], ["sum", "shift"])
        self.assertEqual(impl.methods[0].receiver, "self")
        self.assertEqual(impl.methods[1].receiver, "var self")
        # `self` is not listed among the explicit params.
        self.assertEqual([p.name for p in impl.methods[1].params], ["d"])

    def test_generic_impl_type_params(self):
        prog = parse(tokenize(
            "struct Box<T> { v: T }\n"
            "impl<T> Box<T> { fun get(self) -> T { return self.v } }\n"
        ))
        impl = [d for d in prog.decls if isinstance(d, ast.ImplDecl)][0]
        self.assertEqual(impl.type_params, ["T"])

    def test_method_requires_self(self):
        with self.assertRaises(ParseError):
            parse(tokenize("struct P { x: int }\nimpl P { fun f(a: int) {} }\n"))

    def test_attributes_rejected_on_impl(self):
        with self.assertRaises(ParseError):
            parse(tokenize("struct P { x: int }\n#test\nimpl P { fun f(self) {} }\n"))


class TestChecker(unittest.TestCase):
    def test_method_table_populated(self):
        c = check(parse(tokenize(_POINT)))
        self.assertEqual(set(c.methods["Point"]), {"sum", "shift"})
        # each method is also a lowered function with a dotted (collision-free) name
        self.assertIn("Point.sum", c.functions)
        self.assertEqual(len(c.functions["Point.sum"].params), 1)  # self only

    def test_unknown_method_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(_POINT + "fun g(p: Point) -> int { return p.nope() }\n")))

    def test_duplicate_method_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "struct P { x: int }\n"
                "impl P { fun f(self) -> int { return 1 } }\n"
                "impl P { fun f(self) -> int { return 2 } }\n"
            )))

    def test_method_field_collision_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "struct P { x: int }\nimpl P { fun x(self) -> int { return self.x } }\n"
            )))

    def test_var_self_needs_mutable_receiver(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                _POINT + "fun g() { let p = Point { x: 1, y: 2 }\n    p.shift(3) }\n"
            )))

    def test_reassign_self_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(parse(tokenize(
                "struct P { x: int }\n"
                "impl P { fun r(var self) { self = P { x: 0 } } }\n"
            )))


class TestInterpreter(unittest.TestCase):
    def test_var_self_writes_back(self):
        src = _POINT + (
            "fun main() {\n    var p = Point { x: 1, y: 2 }\n"
            "    p.shift(5)\n    print(p.sum())\n}\n"
        )
        self.assertEqual(run_src(src), "8\n")

    def test_read_only_self_preserves_value_semantics(self):
        src = (
            "struct P { x: int }\n"
            "impl P { fun with(self, v: int) -> P { return P { x: v } }\n"
            "         fun x_of(self) -> int { return self.x } }\n"
            "fun main() {\n    let a = P { x: 1 }\n    let b = a.with(9)\n"
            "    print(a.x_of())\n    print(b.x_of())\n}\n"
        )
        self.assertEqual(run_src(src), "1\n9\n")

    def test_generic_method_dispatch(self):
        src = (
            "struct Box<T> { v: T }\n"
            "impl<T> Box<T> { fun get(self) -> T { return self.v }\n"
            "                 fun set(var self, x: T) { self.v = x } }\n"
            "fun main() {\n    var b = Box { v: 7 }\n    b.set(42)\n    print(b.get())\n}\n"
        )
        self.assertEqual(run_src(src), "42\n")

    def test_method_on_builtin(self):
        src = (
            "impl int { fun double(self) -> int { return self * 2 } }\n"
            "fun main() {\n    let n = 21\n    print(n.double())\n}\n"
        )
        self.assertEqual(run_src(src), "42\n")


if __name__ == "__main__":
    unittest.main()
