"""Unit tests for the Myla tree-walking interpreter (docs/architecture.md §6)."""
import io
import unittest

from myla.errors import MylaRuntimeError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check


def run_src(src: str) -> str:
    checker = check(parse(tokenize(src)))
    out = io.StringIO()
    Interpreter(checker, out).run()
    return out.getvalue()


def run_main(body: str, pre: str = "") -> str:
    return run_src(f"{pre}fun main() {{\n    {body}\n}}\n")


class TestBasics(unittest.TestCase):
    def test_print_int_bool_str(self):
        self.assertEqual(run_main('print(42)\n    print(true)\n    print("hi")'),
                         "42\ntrue\nhi\n")

    def test_arithmetic(self):
        self.assertEqual(run_main("print(2 + 3 * 4)"), "14\n")

    def test_let_and_var(self):
        self.assertEqual(run_main("let x = 5\n    var y = x + 1\n    y = y * 2\n    print(y)"),
                         "12\n")


class TestIntegerWrapping(unittest.TestCase):
    def test_uint8_wraps(self):
        self.assertEqual(run_main("var b: uint8 = 255u8\n    b = b + 1u8\n    print(b)"), "0\n")

    def test_int8_wraps(self):
        self.assertEqual(run_main("var b: int8 = 127i8\n    b = b + 1i8\n    print(b)"), "-128\n")

    def test_negative_literal(self):
        self.assertEqual(run_main("let x: int8 = -128i8\n    print(x)"), "-128\n")


class TestDivisionSemantics(unittest.TestCase):
    def test_truncation_toward_zero(self):
        self.assertEqual(run_main("print(7 / 2)"), "3\n")
        self.assertEqual(run_main("print(-7 / 2)"), "-3\n")  # trunc, not floor

    def test_modulo_sign(self):
        self.assertEqual(run_main("print(-7 % 2)"), "-1\n")

    def test_division_by_zero(self):
        with self.assertRaises(MylaRuntimeError):
            run_main("var z = 0\n    print(1 / z)")


class TestControlFlow(unittest.TestCase):
    def test_if_else(self):
        self.assertEqual(
            run_main('if 1 < 2 {\n        print("a")\n    } else {\n        print("b")\n    }'),
            "a\n",
        )

    def test_while(self):
        self.assertEqual(
            run_main("var i = 0\n    while i < 3 {\n        print(i)\n        i = i + 1\n    }"),
            "0\n1\n2\n",
        )

    def test_for_range_half_open(self):
        self.assertEqual(
            run_main("for i in 0..3 {\n        print(i)\n    }"),
            "0\n1\n2\n",
        )


class TestFunctions(unittest.TestCase):
    def test_recursion(self):
        src = (
            "fun fact(n: int) -> int {\n"
            "    if n <= 1 {\n        return 1\n    }\n"
            "    return n * fact(n - 1)\n}\n"
        )
        self.assertEqual(run_src(src + "fun main() {\n    print(fact(5))\n}\n"), "120\n")


class TestPartialApplication(unittest.TestCase):
    def test_filled_arguments_are_evaluated_once_when_made(self):
        # D51, D60 (MYLA-75): callee, receiver and filled arguments run once,
        # left to right, when the partial is made; a variable is its value then
        pre = ("struct C { n: int }\nimpl C {\n    fun add(self, a: int, b: int) -> int {\n"
               "        return self.n + a + b\n    }\n}\n"
               "fun f(x: int) -> int {\n    print(x)\n    return x\n}\n"
               "fun c(n: int) -> C {\n    print(n)\n    return C { n: n }\n}\n"
               "fun g(a: int, b: int, c: int) -> int {\n    return a * 100 + b * 10 + c\n}\n")
        body = ("let p = g(f(1), _, f(2))\n    print(0)\n    print(p(f(3)))\n    print(p(4))\n"
                "    let m = c(5).add(f(6), _)\n    print(0)\n    print(m(7))\n    print(m(8))\n"
                "    var x = 1\n    let r = g(x, _, 3)\n    x = 2\n    print(r(0))")
        self.assertEqual(run_main(body, pre).split(), [
            "1", "2", "0", "3", "132", "142",
            "5", "6", "0", "18", "19",
            "103"])


class TestStructValueSemantics(unittest.TestCase):
    PRE = "struct P {\n    x: int,\n    y: int,\n}\n"

    def test_copy_on_assignment(self):
        body = (
            "var a = P { x: 1, y: 2 }\n"
            "    var b = a\n"
            "    b.x = 99\n"
            "    print(a.x)\n"
            "    print(b.x)"
        )
        self.assertEqual(run_main(body, pre=self.PRE), "1\n99\n")

    def test_field_read_and_write(self):
        body = "var p = P { x: 0, y: 0 }\n    p.x = 7\n    print(p.x)"
        self.assertEqual(run_main(body, pre=self.PRE), "7\n")


class TestTestRunner(unittest.TestCase):
    def _run_tests(self, src: str):
        checker = check(parse(tokenize(src)))
        return Interpreter(checker, io.StringIO()).run_tests()

    def test_passing_and_failing(self):
        src = (
            "#test(1, 2)[3]\n"
            "#test(2, 2)[5]\n"  # wrong on purpose
            "fun add(a: int, b: int) -> int {\n    return a + b\n}\n"
        )
        results = self._run_tests(src)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].passed)
        self.assertFalse(results[1].passed)

    def test_no_tests(self):
        self.assertEqual(self._run_tests("fun main() {\n    print(1)\n}\n"), [])


if __name__ == "__main__":
    unittest.main()
