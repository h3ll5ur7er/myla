"""Going on after a declaration's error (MYLA-110, D84).

Each declaration phase records the error of a part and goes on: the part takes
the error type (a parameter, field, payload, alias or const of a bad type) or
is left out (a duplicate, an impl that can't be added). Bodies are checked as
before; where one depends on the error type its check ends without an error,
so no error follows from another, and the first error stays the one a
single-error run reports."""
import unittest

from myla.errors import MylaError
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check


def _errors(source: str) -> list[MylaError]:
    try:
        check(parse(tokenize(source)))
    except MylaError as err:
        return [err, *err.more]
    return []


def _messages(source: str) -> list[str]:
    return [e.message for e in _errors(source)]


BAD = "cannot assign value of type 'bool' to binding of type 'int32'"
LATER = "fun later() {\n    let x: int = true\n}\n"


class RecoveryTests(unittest.TestCase):
    def assertRecovers(self, source: str, first: list[str]) -> None:
        """`source` reports the errors `first`, then `later`'s, and nothing
        mentions the error type."""
        msgs = _messages(source + LATER + "fun main() {}\n")
        self.assertEqual(msgs, first + [BAD])
        self.assertFalse([m for m in msgs if "{error}" in m])

    def test_a_parameter_of_an_unknown_type(self):
        self.assertRecovers(
            "fun f(a: Nope, b: int) -> int {\n    return a + b\n}\n"
            "fun g() -> int {\n    return f(\"anything\", 2) + f(1, 2)\n}\n",
            ["unknown type 'Nope'"])

    def test_an_argument_for_a_good_parameter_is_still_checked(self):
        msgs = _messages("fun f(a: Nope, b: int) -> int {\n    return b\n}\n"
                         "fun main() {\n    print(f(1, \"two\"))\n}\n")
        self.assertEqual(msgs, ["unknown type 'Nope'",
                                "argument type mismatch in call to 'f': expected 'int32', found 'str'"])

    def test_a_return_type_of_an_unknown_type(self):
        # the returned value isn't compared; a call's result ends the caller's
        # check, unless it is a statement
        self.assertRecovers(
            "fun f() -> Nope {\n    return 1\n}\n"
            "fun g() {\n    f()\n    let y: int = f()\n}\n",
            ["unknown type 'Nope'"])

    def test_a_statement_call_does_not_end_the_check(self):
        msgs = _messages("fun f() -> Nope {\n    return 1\n}\n"
                         "fun main() {\n    f()\n    let y: int = true\n}\n")
        self.assertEqual(msgs, ["unknown type 'Nope'", BAD])

    def test_a_field_of_an_unknown_type(self):
        self.assertRecovers(
            "struct S { a: Nope, b: int }\n"
            "fun g(s: S) -> int {\n    let t = S { a: true, b: 2 }\n    return s.a + t.b\n}\n",
            ["unknown type 'Nope'"])

    def test_a_payload_of_an_unknown_type(self):
        self.assertRecovers(
            "enum E { A(Nope), B(int) }\n"
            "fun g(e: E) -> int {\n    let x = E.A(3)\n"
            "    return match e {\n        A(v) => v,\n        B(n) => n,\n    }\n}\n",
            ["unknown type 'Nope'"])

    def test_a_failed_alias_is_one_error(self):
        self.assertRecovers(
            "typealias A = Nope\ntypealias B = [A]\n"
            "fun g(b: B) -> int {\n    let c: A = 1\n    return len(b)\n}\n",
            ["unknown type 'Nope'"])

    def test_an_alias_of_a_later_failing_alias_is_one_error(self):
        self.assertRecovers("typealias A = [B]\ntypealias B = Nope\nfun g(a: A) {}\n",
                            ["unknown type 'Nope'"])

    def test_a_duplicate_struct_keeps_the_first(self):
        self.assertRecovers(
            "struct P { x: int }\nstruct P { y: str }\n"
            "fun g() -> int {\n    let p = P { x: 1 }\n    return p.x\n}\n",
            ["duplicate top-level declaration 'P'"])

    def test_a_redefined_builtin_is_left_out_with_its_calls(self):
        self.assertRecovers("fun assert(a: int, b: int) {}\nfun g() {\n    assert(1, 2)\n}\n",
                            ["cannot redefine builtin 'assert'"])

    def test_a_failed_const_and_the_consts_folded_from_it(self):
        self.assertRecovers(
            "const A: int = 1 / 0\nconst B: int = A + 1\nconst C: Nope = 1\n"
            "fun g() -> int {\n    return A + B\n}\nfun h() {\n    let c = C\n}\n",
            ["const division by zero", "unknown type 'Nope'"])

    def test_a_const_cycle_is_one_error(self):
        self.assertRecovers("const A: int = B\nconst B: int = A\nfun g() -> int {\n    return A\n}\n",
                            ["const 'A' is defined in terms of itself"])

    def test_a_trait_method_of_an_unknown_type(self):
        self.assertRecovers(
            "trait T {\n    fun f(self, x: Nope) -> int\n}\nstruct S { a: int }\n"
            "impl T for S {\n    fun f(self, x: int) -> int {\n        return x\n    }\n}\n"
            "fun g(s: S) -> int {\n    return s.f(1)\n}\n",
            ["unknown type 'Nope'"])

    def test_an_impl_that_does_not_conform_breaks_the_operator(self):
        self.assertRecovers(
            "struct V { a: int }\n"
            "impl Add for V {\n    fun add(self) -> V {\n        return self\n    }\n}\n"
            "fun g(v: V) -> V {\n    return v + v\n}\n",
            ["method 'add' in impl of trait 'Add' for 'V' does not match the trait signature "
             "(expected '(V) -> V')"])

    def test_an_impl_of_an_unknown_type(self):
        self.assertRecovers("impl Nope {\n    fun f(self) -> int {\n        return true\n    }\n}\n",
                            ["unknown type 'Nope'"])

    def test_a_duplicate_impl_is_left_out(self):
        self.assertRecovers(
            "struct S { a: int }\n#derive(Eq)\nstruct Q { a: int }\n"
            "impl Eq for S {\n    fun eq(self, o: S) -> bool {\n        return true\n    }\n}\n"
            "impl Eq for S {\n    fun eq(self, o: S) -> bool {\n        return 1\n    }\n}\n"
            "fun g(s: S) -> bool {\n    return s == s\n}\n",
            ["duplicate impl of trait 'Eq' for type 'S' (at most one user impl per trait/type pair)"])

    def test_a_method_colliding_with_a_field_is_left_out(self):
        self.assertRecovers(
            "struct S { a: int }\nimpl S {\n    fun a(self) -> int {\n        return true\n    }\n}\n",
            ["method 'a' collides with a field of 'S'"])

    def test_a_bad_bound_skips_the_function(self):
        self.assertRecovers(
            "fun f<T: Nope>(a: T) -> T {\n    return a.anything()\n}\n"
            "fun g() -> int {\n    return f(1)\n}\n",
            ["unknown trait 'Nope' in bound 'T: Nope'"])

    def test_the_first_error_is_unchanged(self):
        # a single-error run reported the alias first: it still comes first
        msgs = _messages("fun f(a: Gone) {}\nstruct S { b: Lost }\ntypealias T = Nope\n"
                         "fun main() {\n    let x: int = true\n}\n")
        self.assertEqual(msgs, ["unknown type 'Nope'", "unknown type 'Lost'",
                                "unknown type 'Gone'", BAD])

    def test_an_import_checked_alone_is_left_out(self):
        self.assertRecovers("import nowhere\n", [
            "imports need the module loader: this file was type-checked on its own "
            "(use 'myla check' or 'myla run')"])


if __name__ == "__main__":
    unittest.main()
