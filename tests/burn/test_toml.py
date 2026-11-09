"""Burn tests: `std.toml` (MYLA-89) against Python's `tomllib`.

The driver (`DRIVER`) reads length-framed documents from
stdin and prints, for each, `ok <value as compact JSON>` or `err <line> <col>
<message>`. Python generates documents of the subset from a seed (tables,
dotted and quoted headers, bare, quoted and literal keys, strings with
escapes and non-ASCII characters, int64 limits with `_` and signs, booleans,
string arrays over several lines with comments and trailing commas, nested
inline tables, comments, CRLF, random spacing), and broken ones by deleting,
inserting or duplicating a character or cutting the text short. For each:

- when `tomllib` rejects it, `std.toml` must reject it too;
- when `tomllib` accepts it, `std.toml` must give the same value, or reject it
  as outside the subset ("… not supported", "arrays may only hold strings");
  generated documents of the subset that `tomllib` accepts must be accepted
  with the same value (a few repeat a key or a table by chance, and both
  reject those).

The writer (MYLA-402): every document `std.toml` reads, it writes with
`to_string`; the driver checks that `parse` reads that back as the same value,
and `tomllib` must read it as the original's value, keys in order. Random
values beyond the subset (arrays of tables, arrays of any values) are written
and read by `tomllib` alone. With MYLA_TOML_TEST naming a checkout of
toml-test, its valid TOML 1.0 files run as well.

The big corpus runs on the self-hosted native build, a small one in the
self-hosted interpreter. (The Python toolchain's backend and interpreter ran
them as well until it was retired, MYLA-219.)
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import tempfile
import tomllib
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

# The driver was shared with the unit tests of the retired Python toolchain
# (`tests/unit/test_toml.py`).
DRIVER = """from std.io import stdin, println, Reader
from std.toml import parse, Toml, TomlError
import std.toml as toml
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
            for x in items { out.push(to_json(x)) }
            Json.Array(out)
        }
        Toml.Table(members) => {
            var out: [(str, Json)] = []
            for m in members { out.push((m.0, to_json(m.1))) }
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
                    // the value, a tab, the text `std.toml` writes, if it
                    // reads back as the value (MYLA-402)
                    Ok(v) => {
                        let written = toml.to_string(v)
                        let back = match parse(written) {
                            Ok(w) => w == v,
                            Err(e) => false,
                        }
                        let tail = match back { true => "\\t", false => "\\tnot read back as itself: " }
                        println("ok " + to_string(to_json(v)) + tail + to_string(Json.Str(written)))
                    },
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


INT64_MIN, INT64_MAX = -(2 ** 63), 2 ** 63 - 1

_CHARS = ["a", "z", "Q", " ", "\t", '"', "'", "\\", "#", "=", "[", "]", "{", "}", ",", ".",
          "\n", "\r", "\b", "\f", "\x00", "\x1f", "\x7f", "é", "λ", "€", "😀", "𝄞", " "]


def _string_value(rng: random.Random) -> str:
    return "".join(rng.choice(_CHARS) for _ in range(rng.randrange(0, 8)))


def _quote(rng: random.Random, s: str) -> str:
    """`s` as a basic or (when it can be) a literal string."""
    literal_ok = "'" not in s and all(c == "\t" or (ord(c) >= 32 and c != "\x7f") for c in s)
    if literal_ok and rng.random() < 0.3:
        return "'" + s + "'"
    out = []
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c in "\b\t\n\f\r" and rng.random() < 0.8:
            out.append({"\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}[c])
        elif c == "\t":
            out.append("\t")
        elif ord(c) < 32 or c == "\x7f":
            out.append(f"\\u{ord(c):04x}" if rng.random() < 0.5 else f"\\U{ord(c):08X}")
        elif ord(c) > 127 and rng.random() < 0.3:
            out.append(f"\\u{ord(c):04X}" if ord(c) < 0x10000 else f"\\U{ord(c):08x}")
        else:
            out.append(c)
    return '"' + "".join(out) + '"'


def _key(rng: random.Random) -> str:
    """A key as written: bare, or quoted with characters a bare key can't hold."""
    r = rng.random()
    if r < 0.7:
        return "".join(rng.choice("abcxyz019_-") for _ in range(rng.randrange(1, 5)))
    return _quote(rng, _string_value(rng) if r < 0.9 else rng.choice(["a", "b", "x"]))


def _integer(rng: random.Random) -> str:
    n = rng.choice([0, 1, -1, 7, 42, -300, INT64_MIN, INT64_MAX, rng.randrange(INT64_MIN, INT64_MAX),
                    rng.randrange(-10 ** 6, 10 ** 6)])
    text = str(abs(n))
    if len(text) > 3 and rng.random() < 0.3:          # 1_000_000
        groups = []
        while text:
            groups.insert(0, text[-3:])
            text = text[:-3]
        text = "_".join(groups)
    sign = "-" if n < 0 else ("+" if rng.random() < 0.1 else "")
    return sign + text


def _ws(rng: random.Random) -> str:
    return rng.choice(["", " ", " ", "  ", "\t"])


def _value(rng: random.Random, depth: int) -> str:
    kind = rng.choice(["str", "str", "int", "bool", "array"] + (["inline"] if depth < 2 else []))
    if kind == "str":
        return _quote(rng, _string_value(rng))
    if kind == "int":
        return _integer(rng)
    if kind == "bool":
        return rng.choice(["true", "false"])
    if kind == "array":
        items = [_quote(rng, _string_value(rng)) for _ in range(rng.randrange(0, 4))]
        if rng.random() < 0.5:
            sep = "," + rng.choice([" ", "\n  ", " # note\n  ", "\n\n"])
            trailing = "," if items and rng.random() < 0.4 else ""
            return "[" + rng.choice(["", "\n  "]) + sep.join(items) + trailing + rng.choice(["", "\n"]) + "]"
        return "[" + _ws(rng) + ", ".join(items) + _ws(rng) + "]"
    keys = []
    pairs = []
    for _ in range(rng.randrange(0, 4)):
        k = _key(rng)
        if k not in keys:
            keys.append(k)
            pairs.append(f"{k}{_ws(rng)}={_ws(rng)}{_value(rng, depth + 1)}")
    return "{" + _ws(rng) + ", ".join(pairs) + _ws(rng) + "}"


def _key_values(rng: random.Random, lines: list[str]) -> None:
    used: set[str] = set()
    for _ in range(rng.randrange(0, 4)):
        k = _key(rng)
        if k in used:
            continue
        used.add(k)
        comment = rng.choice(["", "", " # comment", "\t#λ"])
        lines.append(f"{_ws(rng)}{k}{_ws(rng)}={_ws(rng)}{_value(rng, 0)}{_ws(rng)}{comment}")


def _document(rng: random.Random) -> str:
    lines: list[str] = []
    if rng.random() < 0.3:
        lines.append("# a document")
    _key_values(rng, lines)
    for _ in range(rng.randrange(0, 4)):
        path = [_key(rng) for _ in range(rng.randrange(1, 4))]
        lines.append("")
        lines.append(_ws(rng) + "[" + _ws(rng) + (_ws(rng) + "." + _ws(rng)).join(path) + _ws(rng) + "]"
                     + rng.choice(["", " # table"]))
        _key_values(rng, lines)
    newline = "\r\n" if rng.random() < 0.1 else "\n"
    return newline.join(lines) + rng.choice(["", newline])


def _valid_documents(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    return [_document(rng) for _ in range(count)]


def _broken_documents(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    noise = list("[]{}=,.\"'#\\ \t0123456789-_+:aetfnxuU") + ["\n", "\r", "é", "\x00", "\x7f", '"""']
    texts = []
    while len(texts) < count:
        text = _document(rng)
        if not text:
            continue
        i = rng.randrange(len(text) + 1)
        how = rng.randrange(4)
        if how == 0 and i < len(text):
            text = text[:i] + text[i + 1:]
        elif how == 1:
            text = text[:i] + rng.choice(noise) + text[i:]
        elif how == 2 and i < len(text):
            text = text[:i] + text[i] + text[i:]
        else:
            text = text[:i]
        texts.append(text)
    return texts


def _outside_subset(value) -> bool:
    """Whether `tomllib`'s value holds something the subset can't: a float, a
    date or time, an array of other values than strings, an integer beyond
    int64."""
    if isinstance(value, bool) or isinstance(value, str):
        return False
    if isinstance(value, int):
        return not INT64_MIN <= value <= INT64_MAX
    if isinstance(value, list):
        return any(not isinstance(v, str) for v in value)
    if isinstance(value, dict):
        return any(_outside_subset(v) for v in value.values())
    return True


def _verdict(text: str) -> tuple[str, str | None]:
    """("err", None) when tomllib rejects `text`; ("outside", None) when it
    reads a value the subset can't hold; else ("ok", the driver's line)."""
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return "err", None
    if _outside_subset(value):
        return "outside", None
    return "ok", "ok " + canonical(value)


def _outside_message(line: str) -> bool:
    return line.startswith("err ") and ("not supported" in line or "arrays may only hold strings" in line
                                        or "integer out of range" in line)


def _ordered(value):
    """`value` with its tables as lists of pairs, so that comparing two
    compares the order of their keys too, and its scalars with their types."""
    if isinstance(value, dict):
        return [(k, _ordered(v)) for k, v in value.items()]
    if isinstance(value, list):
        return [_ordered(v) for v in value]
    return (type(value).__name__, value)


def _written_ok(text: str, written: str) -> bool:
    """Whether `written`, the driver's JSON string of what `std.toml` wrote for
    the document `text` (MYLA-402), is TOML that `tomllib` reads as the same
    value, keys in the same order (the driver checked that `std.toml` reads
    it back as the same value)."""
    if written.startswith("not read back"):
        return False
    return _ordered(tomllib.loads(json.loads(written))) == _ordered(tomllib.loads(text))


# Writes TOML for values beyond the subset (MYLA-402): reads length-framed
# JSON values and prints, for each, what `std.toml` writes, as a JSON string.
WRITER_DRIVER = DRIVER.split("fun main()")[0].replace(
    "from std.json import Json, to_string", "from std.json import Json, to_string\nimport std.json as json") + """
fun to_toml(j: Json) -> Toml {
    return match j {
        Json.Str(s) => Toml.Str(s)
        Json.Int(n) => Toml.Int(n)
        Json.Bool(b) => Toml.Bool(b)
        Json.Array(items) => {
            var out: [Toml] = []
            for x in items { out.push(to_toml(x)) }
            Toml.Array(out)
        }
        Json.Object(members) => {
            var out: [(str, Toml)] = []
            for m in members { out.push((m.0, to_toml(m.1))) }
            Toml.Table(out)
        }
        _ => Toml.Str("not a TOML value")
    }
}

fun main() {
    var input = Input { r: stdin() }
    while let Some(text) = input.next() {
        match json.parse(text) {
            Ok(j) => { println(to_string(Json.Str(toml.to_string(to_toml(j))))) },
            Err(e) => { println("err") },
        }
    }
}
"""


def _any_value(rng: random.Random, depth: int):
    """A value of any kind `std.toml`'s type holds: arrays of any values and
    arrays of tables too."""
    kinds = ["str", "int", "bool"] + (["array", "tables", "table", "table"] if depth < 3 else [])
    kind = rng.choice(kinds)
    if kind == "str":
        return _string_value(rng)
    if kind == "int":
        return rng.choice([0, -1, INT64_MIN, INT64_MAX, rng.randrange(INT64_MIN, INT64_MAX)])
    if kind == "bool":
        return rng.random() < 0.5
    if kind == "array":
        return [_any_value(rng, depth + 1) for _ in range(rng.randrange(0, 4))]
    if kind == "tables":
        return [_any_table(rng, depth + 1) for _ in range(rng.randrange(1, 3))]
    return _any_table(rng, depth + 1)


def _any_table(rng: random.Random, depth: int) -> dict:
    """A table of such values, tables and key/value pairs in any order."""
    out = {}
    for _ in range(rng.randrange(0, 5)):
        r = rng.random()
        key = (_string_value(rng) if r < 0.2 else
               "".join(rng.choice("abxyz_-19") for _ in range(rng.randrange(1, 4))))
        out[key] = _any_value(rng, depth)
    return out


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TomlAgainstPython(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        gen = selfhost_tool("gen_main")
        asm = subprocess.run([gen, path, STDLIB_ROOT], capture_output=True, text=True, check=True)
        sh_native = os.path.join(cls.tmp.name, "sh_native")
        with open(sh_native + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm.stdout)
        subprocess.run(["as", "--64", "-o", sh_native + ".o", sh_native + ".s"], check=True)
        subprocess.run(["ld", "-o", sh_native, sh_native + ".o"], check=True)
        cls.native = {"self-hosted native": [sh_native]}
        writer = os.path.join(cls.tmp.name, "writer.my")
        with open(writer, "w", encoding="utf-8") as fh:
            fh.write(WRITER_DRIVER)
        cls.writer = os.path.join(cls.tmp.name, "writer")
        asm = subprocess.run([gen, writer, STDLIB_ROOT], capture_output=True, text=True, check=True)
        with open(cls.writer + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm.stdout)
        subprocess.run(["as", "--64", "-o", cls.writer + ".o", cls.writer + ".s"], check=True)
        subprocess.run(["ld", "-o", cls.writer, cls.writer + ".o"], check=True)
        cls.interpreters = {
            "self-hosted interpreter": [selfhost_tool("interp_main"), path, STDLIB_ROOT],
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def check(self, implementations: dict[str, list[str]], texts: list[str],
              all_valid: bool = False) -> dict[str, int]:
        """Run `texts` through each implementation and compare with tomllib;
        the number of documents of each verdict."""
        verdicts = [_verdict(t) for t in texts]
        counts: dict[str, int] = {}
        for kind, _ in verdicts:
            counts[kind] = counts.get(kind, 0) + 1
        data = framed(texts)
        for impl, argv in implementations.items():
            with self.subTest(implementation=impl):
                proc = subprocess.run(argv, input=data, capture_output=True, timeout=600)
                self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
                lines = proc.stdout.decode("utf-8").split("\n")[:-1]
                self.assertEqual(len(lines), len(texts))
                wrong = []
                for text, (kind, expected), got in zip(texts, verdicts, lines):
                    if kind == "err":
                        ok = got.startswith("err ")
                    elif kind == "outside":
                        ok = _outside_message(got)
                    else:
                        value, _, written = got.partition("\t")
                        ok = ((value == expected and _written_ok(text, written))
                              or (not all_valid and _outside_message(got)))
                    if not ok:
                        wrong.append(f"{text!r}\n  tomllib: {kind} {(expected or '')[:200]!r}\n  myla:    {got[:200]!r}")
                self.assertEqual(wrong[:5], [], f"{len(wrong)} of {len(texts)} differ")
        return counts

    def test_documents_of_the_subset(self) -> None:
        # some repeat a key or a table by chance, which both must reject
        counts = self.check(self.native, _valid_documents(1, 3000), all_valid=True)
        self.assertGreater(counts.get("ok", 0), 2400, counts)
        self.assertEqual(counts.get("outside", 0), 0, counts)

    def test_broken_documents(self) -> None:
        counts = self.check(self.native, _broken_documents(2, 4000))
        # most break, many survive as valid TOML (a key or a string changed)
        self.assertGreater(counts.get("err", 0), 1500, counts)
        self.assertGreater(counts.get("ok", 0), 500, counts)

    def test_writer_beyond_the_subset(self) -> None:
        # MYLA-402: what `std.toml` writes for any value of its type, arrays
        # of tables and of other values than strings included, is TOML that
        # tomllib reads as that value, keys in order
        rng = random.Random(5)
        values = [_any_table(rng, 0) for _ in range(2000)]
        data = framed([json.dumps(v, ensure_ascii=False) for v in values])
        proc = subprocess.run([self.writer], input=data, capture_output=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        lines = proc.stdout.decode("utf-8").split("\n")[:-1]
        self.assertEqual(len(lines), len(values))
        wrong = []
        headers = 0
        for value, line in zip(values, lines):
            text = json.loads(line)
            headers += text.count("[[")
            try:
                ok = _ordered(tomllib.loads(text)) == _ordered(value)
            except tomllib.TOMLDecodeError as e:
                ok = False
                text += f"  ({e})"
            if not ok:
                wrong.append(f"{value!r}\n  written: {text!r}")
        self.assertEqual(wrong[:5], [], f"{len(wrong)} of {len(values)} differ")
        self.assertGreater(headers, 200)            # arrays of tables were written

    @unittest.skipUnless(os.environ.get("MYLA_TOML_TEST"), "MYLA_TOML_TEST names no checkout of toml-test")
    def test_toml_test_suite(self) -> None:
        # MYLA-402: the valid files of TOML 1.0 in a checkout of
        # https://github.com/toml-lang/toml-test that MYLA_TOML_TEST names,
        # read as tomllib reads them or refused as outside the subset, and
        # those read written back (2026-11-09: 90 of 208 read, 118 outside)
        root = os.path.join(os.environ["MYLA_TOML_TEST"], "tests")
        with open(os.path.join(root, "files-toml-1.0.0"), encoding="utf-8") as fh:
            names = [n for n in fh.read().split() if n.startswith("valid/") and n.endswith(".toml")]
        texts = []
        for name in names:
            with open(os.path.join(root, name), encoding="utf-8", newline="") as fh:
                texts.append(fh.read())
        counts = self.check(self.native, texts)
        self.assertGreater(counts.get("ok", 0), 80, counts)

    def test_interpreters(self) -> None:
        self.check(self.interpreters, _valid_documents(3, 20) + _broken_documents(4, 40))


if __name__ == "__main__":
    unittest.main()
