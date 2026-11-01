"""Unit tests for the Myla tree-walking interpreter (docs/Architecture/Interpreter.md)."""
import io
import unittest

from myla.errors import MylaRuntimeError, TypeCheckError
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


class TestArgumentOrder(unittest.TestCase):
    def test_values_are_taken_before_a_later_argument_writes_them(self):
        # the receiver first, then each argument in order (the reference's
        # evaluation order): a later `var self` call doesn't change what an
        # earlier argument passed (MYLA-237)
        import io as _io
        out = _io.StringIO()
        Interpreter(check(parse(tokenize("struct C {\n    n: int,\n}\nimpl C {\n    fun bump_get(var self) -> int {\n        self.n = self.n + 1\n        return self.n\n    }\n    fun plus(self, k: int) -> int {\n        return self.n * 100 + k\n    }\n    fun with(self, o: C, k: int) -> int {\n        return self.n * 10000 + o.n * 100 + k\n    }\n}\nfun outer(c: C, k: int) -> int {\n    return c.n * 100 + k\n}\n#main\nfun main() {\n    var c = C { n: 1 }\n    print(c.plus(c.bump_get()))\n    var d = C { n: 1 }\n    print(outer(d, d.bump_get()))\n    var xs = [C { n: 1 }]\n    print(xs[0].plus(xs[0].bump_get()))\n    var e = C { n: 1 }\n    var f = C { n: 5 }\n    print(e.with(f, f.bump_get()))\n    let g = (x: C, k: int) => x.n * 100 + k\n    var h = C { n: 1 }\n    print(g(h, h.bump_get()))\n    var p = C { n: 1 }\n    print(p.n * 100 + p.bump_get())\n}\n"))), out).run()
        self.assertEqual(out.getvalue(), "102\n102\n102\n10506\n102\n102\n")


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

    def test_method_cases(self):
        # D116: the receiver is the first argument; a `var self` method's
        # result is compared, its changed receiver isn't; cases run in source
        # order
        src = (
            "struct C {\n    n: int,\n}\n"
            "#test(2)[2]\nfun first(x: int) -> int {\n    return x\n}\n"
            "impl C {\n"
            "    #test(C { n: 2 }, 3)[5]\n"
            "    #test(C { n: 2 }, 3)[6]\n"
            "    fun add(self, k: int) -> int {\n        return self.n + k\n    }\n"
            "    #test(C { n: 1 })[2]\n"
            "    fun bump(var self) -> int {\n        self.n = self.n + 1\n        return self.n\n    }\n"
            "}\n"
            "#test(1)[1]\nfun last(x: int) -> int {\n    return x\n}\n"
        )
        results = self._run_tests(src)
        self.assertEqual([(r.function, r.index, r.passed) for r in results],
                         [("first", 1, True), ("C.add", 1, True), ("C.add", 2, False),
                          ("C.bump", 1, True), ("last", 1, True)])
        self.assertEqual(results[2].detail, "expected 6, got 5")

    def test_no_tests(self):
        self.assertEqual(self._run_tests("fun main() {\n    print(1)\n}\n"), [])

    def test_exit_in_a_test_fails_it(self):
        # `exit` in a test fails that test; the rest still run (MYLA-81)
        src = ("from std.process import exit\n"
               "#test()[1]\nfun quits() -> int {\n    exit(3)\n    return 1\n}\n"
               "#test()[2]\nfun two() -> int {\n    return 2\n}\n")
        import os, tempfile
        from myla.loader import default_stdlib_root, link
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "quits.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)
            checker = check(link(path, stdlib_root=default_stdlib_root()))
        results = Interpreter(checker, io.StringIO()).run_tests()
        self.assertEqual([(r.function, r.passed, r.detail) for r in results],
                         [("quits", False, "exited with status 3"), ("two", True, "")])


if __name__ == "__main__":
    unittest.main()


class TestAppendRange(unittest.TestCase):
    """`append(sb, s, start, end)` appends the bytes s[start..end] (MYLA-85)."""

    def test_appends_the_range(self):
        self.assertEqual(run_main(
            'var sb = StringBuilder()\n'
            '    append(sb, "hello world", 6, 11)\n'
            '    append(sb, "hello world", 0, 0)\n'
            '    append(sb, "-", 0, 1)\n'
            '    append(sb, "hello world", 0, 5)\n'
            '    print(build(sb))'), "world-hello\n")

    def test_a_split_character_is_whole_again_when_joined(self):
        self.assertEqual(run_main(
            'var sb = StringBuilder()\n'
            '    append(sb, "aö", 0, 2)\n'
            '    append(sb, "aö", 2, 3)\n'
            '    let s = build(sb)\n'
            '    print(s == "aö")\n'
            '    print(s)'), "true\naö\n")

    def test_out_of_bounds(self):
        for start, end in [(-1, 2), (2, 1), (0, 6), (6, 6)]:
            with self.subTest(start=start, end=end):
                with self.assertRaises(MylaRuntimeError) as cm:
                    run_main(f'var sb = StringBuilder()\n    append(sb, "hello", {start}, {end})')
                self.assertIn(f"string range {start}..{end} out of bounds (len 5)", str(cm.exception))

    def test_type_errors(self):
        for args, message in [('"x", 0', "append() takes 2 or 4 argument(s)"),
                              ('"x", "0", 1', "append start"),
                              ('"x", 0, 1u8', "append end"),
                              ('42, 0, 1', "append value")]:
            with self.subTest(args=args):
                with self.assertRaises(TypeCheckError) as cm:
                    run_main(f'var sb = StringBuilder()\n    append(sb, {args})')
                self.assertIn(message, str(cm.exception))

