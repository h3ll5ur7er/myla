"""Unit tests for `std.toml` (MYLA-89): the TOML subset of D73.

`DRIVER` reads length-framed documents from stdin and prints, for each,
`ok <the value as compact JSON>` or `err <line> <col> <message>`; the burn
test `tests/burn/test_toml.py` runs it on random documents against Python's
`tomllib`. Here it runs in the Python interpreter on hand-written documents:
every construct of the subset (compared with `tomllib`), and every error with
its message and position."""
import io
import json
import os
import tempfile
import tomllib
import unittest

from myla.interpreter import Interpreter
from myla.loader import default_stdlib_root, link
from myla.types import check

DRIVER = """from std.io import stdin, println, Reader
from std.toml import parse, Toml, TomlError
from std.json import Json, to_string
from std.num import parse_int

struct Input { r: Reader }

impl Input {
    // The next document: a line with its length in bytes, then the text.
    fun next(var self) -> Option<str> {
        let header = match self.r.read_line() {
            Ok(Some(line)) => line,
            _ => "",
        }
        let n = match parse_int(header) {
            Some(v) => v as int32,
            None => -1,
        }
        if n < 0 { return None }
        return match self.r.read_exact(n) {
            Ok(Some(t)) => Some(t),
            _ => None,
        }
    }
}

fun to_json(t: Toml) -> Json {
    return match t {
        Toml.Str(s) => Json.Str(s)
        Toml.Int(n) => Json.Int(n)
        Toml.Bool(b) => Json.Bool(b)
        Toml.Array(items) => {
            var out: [Json] = []
            for x in items { push(out, to_json(x)) }
            Json.Array(out)
        }
        Toml.Table(members) => {
            var out: [(str, Json)] = []
            for m in members { push(out, (m.0, to_json(m.1))) }
            Json.Object(out)
        }
    }
}

fun main() {
    var input = Input { r: stdin() }
    var more = true
    while more {
        match input.next() {
            Some(text) => {
                match parse(text) {
                    Ok(v) => { println("ok " + to_string(to_json(v))) },
                    Err(e) => { println(format("err {} {} {}", e.line, e.col, e.msg)) },
                }
            },
            None => { more = false },
        }
    }
}
"""


def framed(texts: list[str]) -> bytes:
    out = bytearray()
    for t in texts:
        data = t.encode("utf-8")
        out += str(len(data)).encode() + b"\n" + data
    return bytes(out)


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def run_driver(texts: list[str]) -> list[str]:
    """The driver's line for each text, in the Python interpreter."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        checker = check(link(path, stdlib_root=default_stdlib_root()))
    out, err = io.StringIO(), io.StringIO()
    code = Interpreter(checker, out, err, stdin=io.BytesIO(framed(texts))).run()
    assert code == 0 and err.getvalue() == "", err.getvalue()
    return out.getvalue().split("\n")[:-1]


# Documents of the subset, each construct at least once. The expected value is
# what `tomllib` makes of them.
VALID = [
    "",
    "# only a comment\n",
    'name = "shapes"\n',
    'a = "x"\r\nb = 1\r\n',
    'key = "value" # a comment\n\n\n',
    "  indented = true\t\n",
    "b = false\nt = true",
    'esc = "q\\" b\\\\ \\b \\t \\n \\f \\r \\u00e9 \\U0001F600 \\u0000"\n',
    "lit = 'C:\\Users\\a \"b\"'\n",
    'utf8 = "λ ö 😀"\n',
    'tab = "a\tb"\n',
    "a = 0\nb = -1\nc = +5\nd = 1_000\ne = -9_223_372_036_854_775_808\nf = 9223372036854775807\ng = -0\n",
    'arr = ["a", \'b\', "c",]\n',
    "empty = []\n",
    'multi = [\n  "one", # first\n  # between\n  "two",\n]\n',
    'nested = { a = 1, b = "x", c = { d = true }, e = ["s"], f = {} }\n',
    "spaced = {   }\n",
    '[package]\nname = "geo"\nversion = "0.1.0"\n\n[dependencies]\njson5 = { git = "https://x", tag = "v1" }\n',
    '[a.b]\nx = 1\n[a]\ny = 2\n',
    '[ a . "b c" . \'d\' ]\nk = 1\n',
    '"quoted key" = 1\n\'lit key\' = 2\n"" = 3\n1234 = 4\n-_- = 5\ntrue = 6\n',
    "[x]\n[x.y]\n[x.z]\n[w]\n",
    "[dependencies.big]\npath = 'vendor/big'\n",
]

# (document, line, column, message) of documents outside the subset.
ERRORS = [
    ("a = 1.5\n", 1, 5, "floats are not supported"),
    ("a = 1e3\n", 1, 5, "floats are not supported"),
    ("a = inf\n", 1, 5, "floats are not supported"),
    ("a = -nan\n", 1, 5, "floats are not supported"),
    ("a = 1979-05-27\n", 1, 5, "dates and times are not supported"),
    ("a = 07:32:00\n", 1, 5, "dates and times are not supported"),
    ("a = 0xff\n", 1, 5, "hexadecimal, octal and binary integers are not supported"),
    ('a = """x"""\n', 1, 5, "multi-line strings are not supported"),
    ("a = '''x'''\n", 1, 5, "multi-line strings are not supported"),
    ("a.b = 1\n", 1, 2, "dotted keys are not supported"),
    ("t = { a.b = 1 }\n", 1, 8, "dotted keys are not supported"),
    ("[[x]]\n", 1, 1, "arrays of tables are not supported"),
    ("a = [1, 2]\n", 1, 6, "arrays may only hold strings"),
    ('a = ["x", 1]\n', 1, 11, "arrays may only hold strings"),
    ("a = 1\na = 2\n", 2, 1, "'a' is defined twice"),
    ('a = 1\n"a" = 2\n', 2, 1, "'a' is defined twice"),
    ("[t]\n[t]\n", 2, 1, "table 't' is defined twice"),
    ("[a.b]\n[a]\n[a]\n", 3, 1, "table 'a' is defined twice"),
    ("[a.b]\nx = 1\n[a]\nb = 2\n", 4, 1, "'a.b' is defined twice"),
    ("a = 1\n[a]\n", 2, 1, "'a' is not a table that can be extended"),
    ("a = {}\n[a.b]\n", 2, 1, "'a' is not a table that can be extended"),
    ("t = { a = 1, a = 2 }\n", 1, 14, "'a' is defined twice"),
    ("t = { a = 1, }\n", 1, 14, "a trailing comma is not allowed in an inline table"),
    ("t = { a = 1\n}\n", 1, 12, "expected ',' or '}' in an inline table"),
    ("a = \n", 1, 5, "expected a value"),
    ("a\n", 1, 2, "expected '=' after a key"),
    ("= 1\n", 1, 1, "expected a key"),
    ("a = 1 b = 2\n", 1, 7, "expected the end of the line"),
    ("a = truex\n", 1, 5, "expected a value"),
    ('a = "abc\n', 1, 5, "unterminated string"),
    ("a = 'abc", 1, 5, "unterminated string"),
    ('a = "\\x"\n', 1, 6, "invalid escape in a string"),
    ('a = "\\ud800"\n', 1, 6, "invalid unicode escape"),
    ('a = "\\U00110000"\n', 1, 6, "invalid unicode escape"),
    ('a = "\\u12"\n', 1, 6, "invalid unicode escape"),
    ('a = "x\x01"\n', 1, 7, "control character in a string"),
    ("# bad \x7f\n", 1, 7, "control character in a comment"),
    ("a = 1\rb = 2\n", 1, 6, "a carriage return must be followed by a line feed"),
    ("a = 01\n", 1, 5, "leading zeros are not allowed"),
    ("a = 1__0\n", 1, 6, "'_' must stand between digits"),
    ("a = _1\n", 1, 5, "expected a value"),
    ("a = 1_\n", 1, 6, "'_' must stand between digits"),
    ("a = 9223372036854775808\n", 1, 5, "integer out of range"),
    ("a = -9223372036854775809\n", 1, 5, "integer out of range"),
    ('a = ["x" "y"]\n', 1, 10, "expected ',' or ']' in an array"),
    ("a = [,]\n", 1, 6, "expected a value"),
    ("[a\n", 1, 3, "expected '.' or ']' in a table header"),
    ("[]\n", 1, 2, "expected a key"),
    ('[a]x = 1\n', 1, 4, "expected the end of the line"),
    ('"""k""" = 1\n', 1, 1, "a key can't be a multi-line string"),
    ("λ = 1\n", 1, 1, "expected a key"),
    ('s = "λλ" x\n', 1, 10, "expected the end of the line"),
    ('ok = 1\n\n  [t]\n  k = "v" # c\n  k = 2\n', 5, 3, "'t.k' is defined twice"),
]


class TestParse(unittest.TestCase):
    def test_valid_documents_mean_what_tomllib_reads(self):
        lines = run_driver(VALID)
        for text, got in zip(VALID, lines):
            with self.subTest(text=text):
                self.assertEqual(got, "ok " + canonical(tomllib.loads(text)))

    def test_errors(self):
        lines = run_driver([e[0] for e in ERRORS])
        for (text, line, col, msg), got in zip(ERRORS, lines):
            with self.subTest(text=text):
                self.assertEqual(got, f"err {line} {col} {msg}")

    def test_tomllib_rejects_the_invalid_ones(self):
        # TOML outside the subset is "not supported", an array of other values
        # than strings, or an integer beyond int64 (which tomllib reads as a
        # big int); every other error is an error for tomllib too.
        for text, _, _, msg in ERRORS:
            with self.subTest(text=text):
                if "not supported" in msg or "only hold strings" in msg or "out of range" in msg:
                    tomllib.loads(text)
                else:
                    with self.assertRaises(tomllib.TOMLDecodeError):
                        tomllib.loads(text)


class TestApi(unittest.TestCase):
    def test_field_and_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "main.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "from std.toml import parse, field, Toml, TomlError\n"
                    "fun name(text: str) -> str {\n"
                    "    let doc = match parse(text) { Ok(d) => d, Err(e) => { return e.msg } }\n"
                    "    return match field(doc, \"package\") {\n"
                    "        Some(pkg) => match field(pkg, \"name\") {\n"
                    "            Some(Toml.Str(s)) => s\n"
                    "            _ => \"no name\"\n"
                    "        }\n"
                    "        None => \"no package\"\n"
                    "    }\n"
                    "}\n"
                    "fun main() {\n"
                    "    print(name(\"[package]\\nname = 'geo'\\n\"))\n"
                    "    print(name(\"[package]\\n\"))\n"
                    "    print(name(\"x = 1\"))\n"
                    "    print(name(\"x = \"))\n"
                    "    match field(Toml.Int(1), \"a\") { Some(v) => print(\"?\"), None => print(\"not a table\") }\n"
                    "}\n")
            checker = check(link(path, stdlib_root=default_stdlib_root()))
        out = io.StringIO()
        Interpreter(checker, out, io.StringIO()).run()
        self.assertEqual(out.getvalue(), "geo\nno name\nno package\nexpected a value\nnot a table\n")

    def test_positions(self):
        # `parse_doc` keeps where keys and values are (MYLA-93): pairs, keys
        # of inline tables, headers (the one that opens a table, else the
        # first that implies it), and columns in characters.
        text = ("# a comment\n"
                "[package]\n"
                "name   =  \"géo\"  # x\n"
                "authors = [\"a\",\n"
                "  \"b\"]\n"
                "[dependencies.big]\n"
                "path = 'v'\n"
                "[dependencies]\n"
                "\"λ\" = { path = \"../λ\", 'x y' = { z = 1 } }\n"
                "[x.y]\n")
        paths = [["package"], ["package", "name"], ["package", "authors"],
                 ["dependencies"], ["dependencies", "big"], ["dependencies", "big", "path"],
                 ["dependencies", "λ"], ["dependencies", "λ", "path"],
                 ["dependencies", "λ", "x y"], ["dependencies", "λ", "x y", "z"], ["x"], ["nothing"]]
        lines = []
        for p in paths:
            arr = "[" + ", ".join(json.dumps(k, ensure_ascii=False) for k in p) + "]"
            lines.append(f"    show(d, {arr})")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "main.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "from std.toml import parse_doc, key_pos, value_pos, TomlDoc, TomlPos\n"
                    "fun at(p: Option<TomlPos>) -> str {\n"
                    "    return match p {\n"
                    "        Some(q) => format(\"{}:{}-{}:{}\", q.line, q.col, q.end_line, q.end_col)\n"
                    "        None => \"-\"\n"
                    "    }\n"
                    "}\n"
                    "fun show(d: TomlDoc, path: [str]) {\n"
                    "    print(format(\"{} {}\", at(key_pos(d, path)), at(value_pos(d, path))))\n"
                    "}\n"
                    "fun main() {\n"
                    f"    let text = {json.dumps(text, ensure_ascii=False)}\n"
                    "    match parse_doc(text) {\n"
                    "        Ok(d) => {\n"
                    + "\n".join(lines) + "\n"
                    "        },\n"
                    "        Err(e) => print(e.msg),\n"
                    "    }\n"
                    "}\n")
            checker = check(link(path, stdlib_root=default_stdlib_root()))
        out = io.StringIO()
        Interpreter(checker, out, io.StringIO()).run()
        self.assertEqual(out.getvalue().splitlines(), [
            "2:1-2:10 2:1-2:10",       # [package]
            "3:1-3:5 3:11-3:16",       # name, "géo" (5 characters)
            "4:1-4:8 4:11-5:7",        # authors, over two lines
            "8:1-8:15 8:1-8:15",       # opened by [dependencies], not [dependencies.big]
            "6:1-6:19 6:1-6:19",
            "7:1-7:5 7:8-7:11",
            "9:1-9:4 9:7-9:43",        # "λ" and its inline table
            "9:9-9:13 9:16-9:22",
            "9:24-9:29 9:32-9:41",
            "9:34-9:35 9:38-9:39",
            "10:1-10:6 10:1-10:6",      # implied by [x.y] only
            "- -",
        ])


if __name__ == "__main__":
    unittest.main()
