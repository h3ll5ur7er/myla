"""Unit tests for the Myla type checker (docs/architecture.md §5)."""
import unittest

from myla.errors import TypeCheckError
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import IntType, check


def check_src(src: str):
    return check(parse(tokenize(src)))


def check_fn(body: str, header: str = "fun f() {", extra: str = ""):
    return check_src(f"{extra}{header}\n    {body}\n}}\n")


class TestValidPrograms(unittest.TestCase):
    def test_minimal(self):
        check_src("fun main() {\n    print(1)\n}\n")

    def test_typealias(self):
        check_src("typealias Byte = uint8\nfun f(b: Byte) -> Byte {\n    return b\n}\n")

    def test_int_alias_interchangeable(self):
        check_src("fun f(a: int, b: int32) -> int {\n    return a + b\n}\n")

    def test_struct_and_field_access(self):
        check_src(
            "struct P {\n    x: int,\n    y: int,\n}\n"
            "fun f(p: P) -> int {\n    return p.x + p.y\n}\n"
        )


class TestIntegerLiterals(unittest.TestCase):
    def test_default_is_int32(self):
        c = check_fn("let x = 5")
        # nothing raised; just ensure it checks
        self.assertIsNotNone(c)

    def test_suffix_typing_and_mismatch(self):
        check_fn("let x: uint8 = 255u8")
        with self.assertRaises(TypeCheckError):
            check_fn("let x: int32 = 5u8")  # uint8 != int32

    def test_literal_too_large(self):
        with self.assertRaises(TypeCheckError):
            check_fn("let x: uint8 = 999")

    def test_literal_adopts_operand_type(self):
        # a is int64; `a + 1` should type 1 as int64 and pass.
        check_src("fun f(a: int64) -> int64 {\n    return a + 1\n}\n")

    def test_mixed_int_types_error(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f(a: int32, b: int64) -> int64 {\n    return a + b\n}\n")


class TestStatementsTypes(unittest.TestCase):
    def test_assign_to_let_fails(self):
        with self.assertRaises(TypeCheckError):
            check_fn("let x = 1\n    x = 2")

    def test_assign_to_var_ok(self):
        check_fn("var x = 1\n    x = 2")

    def test_unknown_name(self):
        with self.assertRaises(TypeCheckError):
            check_fn("let x = y")

    def test_condition_must_be_bool(self):
        with self.assertRaises(TypeCheckError):
            check_fn("if 1 {\n        print(1)\n    }")

    def test_redeclaration_in_scope(self):
        with self.assertRaises(TypeCheckError):
            check_fn("let x = 1\n    let x = 2")

    def test_return_value_from_void(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f() {\n    return 1\n}\n")

    def test_missing_return_value(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f() -> int {\n    return\n}\n")

    def test_for_range_non_int(self):
        with self.assertRaises(TypeCheckError):
            check_fn('for i in 0.."x" {\n        print(i)\n    }')

    def test_missing_return_on_some_path(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f(n: int) -> int {\n    if n > 0 {\n        return 1\n    }\n}\n")

    def test_if_else_chain_is_exhaustive(self):
        check_src(
            "fun f(n: int) -> int {\n"
            "    if n > 0 {\n        return 1\n    } else {\n        return 0\n    }\n}\n"
        )


class TestStructsTypes(unittest.TestCase):
    PRE = "struct P {\n    x: int,\n    y: int,\n}\n"

    def test_unknown_field(self):
        with self.assertRaises(TypeCheckError):
            check_src(self.PRE + "fun f(p: P) -> int {\n    return p.z\n}\n")

    def test_missing_field_in_literal(self):
        with self.assertRaises(TypeCheckError):
            check_src(self.PRE + "fun f() -> P {\n    return P { x: 1 }\n}\n")

    def test_unknown_field_in_literal(self):
        with self.assertRaises(TypeCheckError):
            check_src(self.PRE + "fun f() -> P {\n    return P { x: 1, y: 2, z: 3 }\n}\n")

    def test_good_literal(self):
        check_src(self.PRE + "fun f() -> P {\n    return P { x: 1, y: 2 }\n}\n")


class TestCalls(unittest.TestCase):
    PRE = "fun add(a: int, b: int) -> int {\n    return a + b\n}\n"

    def test_arity_mismatch(self):
        with self.assertRaises(TypeCheckError):
            check_src(self.PRE + "fun f() -> int {\n    return add(1)\n}\n")

    def test_arg_type_mismatch(self):
        with self.assertRaises(TypeCheckError):
            check_src(self.PRE + 'fun f() -> int {\n    return add(1, "x")\n}\n')

    def test_unknown_function(self):
        with self.assertRaises(TypeCheckError):
            check_fn("let x = nope(1)")

    def test_print_arity(self):
        with self.assertRaises(TypeCheckError):
            check_fn("print(1, 2)")

    def test_function_name_as_value(self):
        # v0.4.2: a top-level function name used as a value takes its function
        # type, and may be called indirectly through the binding.
        check_src(
            self.PRE
            + "fun f() -> int {\n    let g = add\n    return g(1, 2)\n}\n"
        )

    def test_function_value_call_arg_mismatch(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                self.PRE
                + 'fun f() -> int {\n    let g = add\n    return g(1, "x")\n}\n'
            )


class TestPipelinesCompositionPartial(unittest.TestCase):
    """v0.4.3 — `|>` pipeline, `>>` composition, `_` partial application."""

    PRE = (
        "fun add(a: int, b: int) -> int {\n    return a + b\n}\n"
        "fun double(n: int) -> int {\n    return n * 2\n}\n"
        "fun inc(n: int) -> int {\n    return n + 1\n}\n"
    )

    def test_pipeline_simple_and_with_args(self):
        check_src(
            self.PRE
            + "fun f() -> int {\n    return 5 |> double |> inc\n}\n"
        )
        check_src(
            self.PRE
            + "fun g() -> int {\n    return 5 |> add(3)\n}\n"
        )

    def test_pipeline_non_callable_rejected(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f() -> int {\n    return 5 |> 3\n}\n")

    def test_composition_of_functions(self):
        check_src(
            self.PRE
            + "fun f() -> int {\n    let h = double >> inc\n    return h(10)\n}\n"
        )

    def test_composition_type_mismatch_rejected(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                "fun ts(n: int) -> str {\n    return \"x\"\n}\n"
                "fun double(n: int) -> int {\n    return n * 2\n}\n"
                "fun f() {\n    let h = ts >> double\n}\n"
            )

    def test_composition_non_function_rejected(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                self.PRE + "fun f() {\n    let h = double >> 5\n}\n"
            )

    def test_integer_shift_still_works(self):
        # `>>` between integers is unaffected by composition (operand-typed, D24).
        check_src("fun f() -> int {\n    return 256 >> 2\n}\n")

    def test_partial_application_holes(self):
        check_src(
            self.PRE
            + "fun f() -> int {\n    let g = add(5, _)\n    return g(10)\n}\n"
        )
        check_src(
            self.PRE
            + "fun f() -> int {\n    let g = add(_, 2)\n    return g(40)\n}\n"
        )

    def test_partial_application_arity_error(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                self.PRE + "fun f() {\n    let g = add(_)\n}\n"
            )

    def test_partial_application_generic_rejected(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                "fun id<T>(x: T) -> T {\n    return x\n}\n"
                "fun f() {\n    let g = id(_)\n}\n"
            )

    def test_bare_underscore_rejected(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f() {\n    let x = _\n}\n")


class TestTypesAndAliases(unittest.TestCase):
    def test_unknown_type(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f(x: Nope) {\n    return\n}\n")

    def test_alias_cycle(self):
        with self.assertRaises(TypeCheckError):
            check_src("typealias A = B\ntypealias B = A\nfun f() {\n    return\n}\n")

    def test_duplicate_decl(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun f() {\n    return\n}\nfun f() {\n    return\n}\n")

    def test_cannot_redefine_print(self):
        with self.assertRaises(TypeCheckError):
            check_src("fun print() {\n    return\n}\n")


class TestAttributesAndEntry(unittest.TestCase):
    def test_unknown_attribute(self):
        with self.assertRaises(TypeCheckError):
            check_src("#bogus\nfun f() {\n    return\n}\n")

    def test_main_with_args(self):
        with self.assertRaises(TypeCheckError):
            check_src("#main(1)\nfun f() {\n    return\n}\n")

    def test_main_with_params_rejected(self):
        with self.assertRaises(TypeCheckError):
            check_src("#main\nfun run(x: int) {\n    return\n}\n")

    def test_test_requires_outputs(self):
        with self.assertRaises(TypeCheckError):
            check_src("#test(1)\nfun f(a: int) -> int {\n    return a\n}\n")

    def test_test_arg_count(self):
        with self.assertRaises(TypeCheckError):
            check_src("#test(1, 2)[3]\nfun f(a: int) -> int {\n    return a\n}\n")

    def test_both_main_attr_and_named_main(self):
        with self.assertRaises(TypeCheckError):
            check_src(
                "#main\nfun run() {\n    return\n}\n"
                "fun main() {\n    return\n}\n"
            )

    def test_entry_detection(self):
        c = check_src("#main\nfun run() {\n    print(1)\n}\n")
        self.assertIsNotNone(c.entry)
        self.assertEqual(c.entry.name, "run")


if __name__ == "__main__":
    unittest.main()
