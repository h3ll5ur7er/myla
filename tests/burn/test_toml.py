"""Burn tests: `std.toml` (MYLA-89) against Python's `tomllib`.

The driver of `tests/unit/test_toml.py` reads length-framed documents from
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

The big corpus runs on the native builds of both backends, a small one in
both interpreters.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import tomllib
import unittest

from myla.compiler import build
from myla.loader import default_stdlib_root

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, check_file
from ._tools import selfhost_tool
from tests.unit.test_toml import DRIVER, canonical, framed

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

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


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TomlAgainstPython(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        py_native = os.path.join(cls.tmp.name, "py_native")
        build(check_file(path), py_native)
        gen = selfhost_tool("gen_main")
        asm = subprocess.run([gen, path, default_stdlib_root()], capture_output=True, text=True, check=True)
        sh_native = os.path.join(cls.tmp.name, "sh_native")
        with open(sh_native + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm.stdout)
        subprocess.run(["as", "--64", "-o", sh_native + ".o", sh_native + ".s"], check=True)
        subprocess.run(["ld", "-o", sh_native, sh_native + ".o"], check=True)
        cls.native = {"python native": [py_native], "self-hosted native": [sh_native]}
        cls.interpreters = {
            "python interpreter": [sys.executable, os.path.join(_REPO, "myla.py"), "run", path],
            "self-hosted interpreter": [selfhost_tool("interp_main"), path, default_stdlib_root()],
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
                        ok = got == expected or (not all_valid and _outside_message(got))
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

    def test_interpreters(self) -> None:
        self.check(self.interpreters, _valid_documents(3, 20) + _broken_documents(4, 40))


if __name__ == "__main__":
    unittest.main()
