"""Optional semicolons (MYLA-76, D61): `;` may stand for the line break that
ends a statement or a declaration, and nowhere else."""
import io
import unittest

from myla.canon import canonical_ast
from myla.errors import ParseError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.tokens import TokenKind as T
from myla.types import check


def ast_of(source: str) -> str:
    return canonical_ast(parse(tokenize(source)))


def run(source: str) -> str:
    out = io.StringIO()
    Interpreter(check(parse(tokenize(source))), out).run()
    return out.getvalue()


# The same program, with line breaks and compactly.
LONG = """\
const A: int = 1
const B: int = 2
struct P { x: int, y: int }
trait Area {
    fun area(self) -> int
    fun twice(self) -> int
}
impl Area for P {
    fun area(self) -> int {
        return self.x * self.y
    }
    fun twice(self) -> int {
        return 2 * self.area()
    }
}
fun f(n: int) -> int {
    if n < 0 {
        return 0
    }
    var t = 0
    for i in 0..n {
        t = t + i
    }
    return t
}
fun main() {
    let p = P { x: A + 2, y: B }
    print(p.area())
    print(p.twice())
    print(f(4))
    return
}
"""

SHORT = """\
const A: int = 1; const B: int = 2
struct P { x: int, y: int }
trait Area { fun area(self) -> int; fun twice(self) -> int }
impl Area for P {
    fun area(self) -> int { return self.x * self.y }; fun twice(self) -> int { return 2 * self.area() }
}
fun f(n: int) -> int { if n < 0 { return 0 }; var t = 0; for i in 0..n { t = t + i }; return t }
fun main() { let p = P { x: A + 2, y: B }; print(p.area()); print(p.twice()); print(f(4)); return; }
"""


class TestSemicolons(unittest.TestCase):
    def test_lexed_as_a_token(self):
        self.assertEqual([t.kind for t in tokenize("a; b")], [T.IDENT, T.SEMI, T.IDENT, T.EOF])

    def test_same_program_as_with_line_breaks(self):
        self.assertEqual(ast_of(SHORT), ast_of(LONG))
        self.assertEqual(run(SHORT), "6\n12\n6\n")

    def test_trailing_and_repeated_semicolons(self):
        src = "fun main() {\n    let x = 1;\n    ;; print(x);\n};\n;\n"
        self.assertEqual(ast_of(src), ast_of("fun main() {\n    let x = 1\n    print(x)\n}\n"))

    def test_bare_return(self):
        self.assertEqual(ast_of("fun main() { return; }"), ast_of("fun main() {\n    return\n}\n"))

    def test_lambda_and_match_arm_blocks(self):
        src = ("fun main() {\n"
               "    let f = (x: int) => { let y = x * 2; return y + 1 }\n"
               "    let v = match f(1) { 3 => { print(1); 10 }, _ => 0 }; print(v)\n"
               "}\n")
        self.assertEqual(run(src), "1\n10\n")

    def test_rejected_inside_expressions_and_lists(self):
        for src, message in (
            ("fun main() { f(1; 2) }", "expected ')', found ';'"),
            ("fun main() { let x = [1; 2] }", "expected ']' to close list literal, found ';'"),
            ("struct S { a: int; b: int }", "expected '}', found ';'"),
            ("fun main() { let x = ; }", "expected an expression, found ';'"),
            ("fun main() { match 1 { 1 => 2; _ => 3 } }", "expected '}' to end match, found ';'"),
            ("fun main() { if true {}; else {} }", "expected an expression, found 'else'"),
        ):
            with self.subTest(src=src):
                with self.assertRaises(ParseError) as cm:
                    parse(tokenize(src))
                self.assertEqual(cm.exception.message, message)

    def test_messages_name_the_semicolon(self):
        with self.assertRaises(ParseError) as cm:
            parse(tokenize("fun main() {\n    let x = 1 let y = 2\n}\n"))
        self.assertEqual(cm.exception.message, "expected newline, ';' or '}', found 'let'")
        with self.assertRaises(ParseError) as cm:
            parse(tokenize("const A: int = 1 const B: int = 2\n"))
        self.assertEqual(cm.exception.message,
                         "expected end of declaration (newline or ';'), found 'const'")


if __name__ == "__main__":
    unittest.main()
