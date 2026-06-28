"""Unit tests for restricted generic traits (v0.5.5, D55).

A `trait` may take type parameters; a type implements it *at most once* (for a
single argument T), so `x.compare(y)` needs no overload resolution. Covers the
parser (`trait Name<T>`, `impl Trait<Args> for T`), the checker (trait param
substitution into conformance, arity, coherence), and interpreter dispatch.
Native parity lives in the burn suite (examples/generic_traits.my).
"""
import io
import unittest

from myla import ast
from myla.errors import TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check

_TRAIT = "trait Comparable<T> {\n    fun compare(self, other: T) -> int32\n}\n"

_MONEY = (
    "struct Money { cents: int32 }\n"
    "impl Comparable<int32> for Money {\n"
    "    fun compare(self, other: int32) -> int32 {\n"
    "        if self.cents < other { return -1 }\n"
    "        if self.cents > other { return 1 }\n"
    "        return 0\n"
    "    }\n"
    "}\n"
)


def run_src(src: str) -> str:
    out = io.StringIO()
    Interpreter(check(parse(tokenize(src))), out).run()
    return out.getvalue()


class TestParser(unittest.TestCase):
    def test_generic_trait_decl_carries_type_params(self):
        prog = parse(tokenize(_TRAIT))
        trait = [d for d in prog.decls if isinstance(d, ast.TraitDecl)][0]
        self.assertEqual(trait.type_params, ["T"])

    def test_generic_impl_for_clause_carries_trait_args(self):
        prog = parse(tokenize(_TRAIT + _MONEY))
        impl = [d for d in prog.decls if isinstance(d, ast.ImplDecl)][0]
        self.assertEqual(impl.trait_name, "Comparable")
        self.assertEqual(impl.target.name, "Money")
        self.assertEqual(len(impl.trait_args), 1)
        self.assertEqual(impl.trait_args[0].name, "int32")


class TestChecker(unittest.TestCase):
    def test_conformance_substitutes_trait_param(self):
        # The trait's `other: T` is checked against the impl's `int32`.
        src = _TRAIT + _MONEY + "fun main() {}\n"
        check(parse(tokenize(src)))  # no error

    def test_conformance_mismatch_on_trait_param(self):
        bad = _MONEY.replace("other: int32", "other: str")
        with self.assertRaises(TypeCheckError) as ctx:
            check(parse(tokenize(_TRAIT + bad + "fun main() {}\n")))
        self.assertIn("does not match the trait signature", str(ctx.exception))
        self.assertIn("(int32) -> int32", str(ctx.exception))

    def test_arity_too_few_args(self):
        bad = _MONEY.replace("impl Comparable<int32>", "impl Comparable")
        with self.assertRaises(TypeCheckError) as ctx:
            check(parse(tokenize(_TRAIT + bad + "fun main() {}\n")))
        self.assertIn("expects 1 type argument(s), got 0", str(ctx.exception))

    def test_args_on_non_generic_trait_rejected(self):
        src = (
            "trait Greet { fun greet(self) -> str }\n"
            "struct P { x: int32 }\n"
            "impl Greet<int32> for P { fun greet(self) -> str { return \"hi\" } }\n"
            "fun main() {}\n"
        )
        with self.assertRaises(TypeCheckError) as ctx:
            check(parse(tokenize(src)))
        self.assertIn("expects 0 type argument(s), got 1", str(ctx.exception))

    def test_coherence_one_impl_per_type_ignores_args(self):
        # Two impls of the same generic trait for one type — even with different
        # arguments — is a coherence error.
        src = (
            _TRAIT + _MONEY
            + "impl Comparable<str> for Money {\n"
            "    fun compare(self, other: str) -> int32 { return 0 }\n"
            "}\n"
            "fun main() {}\n"
        )
        with self.assertRaises(TypeCheckError) as ctx:
            check(parse(tokenize(src)))
        self.assertIn("duplicate impl of trait 'Comparable'", str(ctx.exception))

    def test_distinct_types_pick_distinct_args(self):
        # Money: Comparable<int32>, Name: Comparable<str> — both fine.
        src = (
            _TRAIT + _MONEY
            + "struct Name { text: str }\n"
            "impl Comparable<str> for Name {\n"
            "    fun compare(self, other: str) -> int32 {\n"
            "        if len(self.text) < len(other) { return -1 }\n"
            "        if len(self.text) > len(other) { return 1 }\n"
            "        return 0\n"
            "    }\n"
            "}\n"
            "fun main() {}\n"
        )
        check(parse(tokenize(src)))  # no error

    def test_self_as_trait_param_rejected(self):
        with self.assertRaises(TypeCheckError) as ctx:
            check(parse(tokenize(
                "trait Bad<Self> { fun f(self) -> int32 }\nfun main() {}\n"
            )))
        self.assertIn("cannot use 'Self' as a type parameter", str(ctx.exception))


class TestInterpreter(unittest.TestCase):
    def test_call_dispatches_without_overload_resolution(self):
        src = (
            _TRAIT + _MONEY
            + "fun main() {\n"
            "    let m = Money { cents: 100 }\n"
            "    print(m.compare(100))\n"
            "    print(m.compare(50))\n"
            "    print(m.compare(200))\n"
            "}\n"
        )
        self.assertEqual(run_src(src), "0\n1\n-1\n")


if __name__ == "__main__":
    unittest.main()
