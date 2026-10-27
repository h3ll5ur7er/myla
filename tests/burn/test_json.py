"""Burn tests: `std.json` and `std.num` (MYLA-79) against Python's `json`.

A Myla driver reads length-framed JSON texts from stdin and prints, for each,
`ok <to_string(value)>` or `err <line> <col> <message>`. Python generates the
texts from seeded random values (nested arrays and objects, strings with
escapes, control characters and astral characters, int64 limits, random
float bit patterns) in two spellings, compact UTF-8 and indented ASCII with
`\\u` escapes; the driver's output must be exactly what Python makes of them:
`json.dumps(json.loads(text), ensure_ascii=False, separators=(",", ":"))`,
which also checks that floats are written as their shortest repr. Broken
texts (characters deleted, inserted or duplicated, or the text cut short)
must fail where Python fails, with Python's message and position (3.13's
wording; older Pythons only have to fail too).

The big corpus runs on the native builds of both backends, a small one on
both interpreters. The modules' own `#test` cases run too.
"""
from __future__ import annotations

import json
import math
import os
import random
import struct
import subprocess
import sys
import tempfile
import unittest

from myla.compiler import build
from myla.loader import default_stdlib_root

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, check_file
from ._tools import selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

DRIVER = """from std.io import stdin, println, Reader
from std.json import parse, to_string, JsonError
from std.num import parse_int

struct Input { r: Reader }

impl Input {
    // The next text: a line with its length in bytes, then the text.
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

fun main() {
    var input = Input { r: stdin() }
    var more = true
    while more {
        match input.next() {
            Some(text) => {
                match parse(text) {
                    Ok(v) => { println("ok " + to_string(v)) },
                    Err(e) => { println(format("err {} {} {}", e.line, e.col, e.msg)) },
                }
            },
            None => { more = false },
        }
    }
}
"""

INT64_MIN, INT64_MAX = -(2 ** 63), 2 ** 63 - 1


def _random_float(rng: random.Random, bits: bool = True) -> float:
    if bits and rng.random() < 0.5:
        return struct.unpack("<d", struct.pack("<Q", rng.getrandbits(64)))[0]
    return rng.choice([0.0, -0.0, 0.1, 1.5, 1e16, 1e-7, 123.456, 5e-324, 1.7976931348623157e308,
                       2.0 ** 53, 1e22, 1e23, 9007199254740993.0, float("inf"), float("-inf")])


def _random_string(rng: random.Random) -> str:
    alphabet = ["a", "z", " ", '"', "\\", "/", "\n", "\t", "\r", "\b", "\f", "\x00", "\x1f", "\x7f",
                "é", "λ", " ", "€", "😀", "𝄞", "￿"]
    return "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 12)))


def _random_value(rng: random.Random, depth: int = 0, bits: bool = True):
    kinds = ["null", "bool", "int", "float", "str"] + (["array", "object"] * 2 if depth < 4 else [])
    kind = rng.choice(kinds)
    if kind == "null":
        return None
    if kind == "bool":
        return rng.random() < 0.5
    if kind == "int":
        return rng.choice([0, 1, -1, 42, INT64_MIN, INT64_MAX, rng.randrange(INT64_MIN, INT64_MAX)])
    if kind == "float":
        return _random_float(rng, bits)
    if kind == "str":
        return _random_string(rng)
    if kind == "array":
        return [_random_value(rng, depth + 1, bits) for _ in range(rng.randrange(0, 5))]
    return {_random_string(rng) + str(i): _random_value(rng, depth + 1, bits) for i in range(rng.randrange(0, 5))}


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _has_surrogate(value) -> bool:
    """Whether a parsed value holds a lone surrogate (which Myla rejects)."""
    if isinstance(value, str):
        return any(0xD800 <= ord(c) <= 0xDFFF for c in value)
    if isinstance(value, list):
        return any(_has_surrogate(v) for v in value)
    if isinstance(value, dict):
        return any(_has_surrogate(k) or _has_surrogate(v) for k, v in value.items())
    return False


def _too_big(value) -> bool:
    """Whether a parsed value holds an integer outside int64 (Myla reads it as
    a float)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return not INT64_MIN <= value <= INT64_MAX
    if isinstance(value, list):
        return any(_too_big(v) for v in value)
    if isinstance(value, dict):
        return any(_too_big(v) for v in value.values())
    return False


def _expected(text: str) -> str | None:
    """Python's verdict on `text` as the driver prints it; None to skip it."""
    try:
        value = json.loads(text, object_pairs_hook=_no_duplicates)
    except json.JSONDecodeError as err:
        return f"err {err.lineno} {err.colno} {err.msg}"
    except (RecursionError, _Duplicate):
        return None
    if _has_surrogate(value) or _too_big(value):
        return None
    return "ok " + _canonical(value)


class _Duplicate(Exception):
    """An object with a repeated key: Python keeps the last value at the
    first key's place, Myla keeps both members."""


def _no_duplicates(pairs: list) -> dict:
    d = dict(pairs)
    if len(d) != len(pairs):
        raise _Duplicate()
    return d


def _valid_texts(seed: int, count: int, bits: bool = True) -> list[str]:
    """Random values as texts; `bits`: floats from random bit patterns too
    (their exact digits take big integers, slow when interpreted)."""
    rng = random.Random(seed)
    texts = []
    for _ in range(count):
        value = _random_value(rng, 0, bits)
        texts.append(_canonical(value))
        texts.append(json.dumps(value, indent=2))          # ASCII, \\u escapes, whitespace
    return texts


def _broken_texts(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    texts = []
    noise = list('[]{}:,"\\ 0-.eE+tfnu') + ["\n", "é"]
    while len(texts) < count:
        text = _canonical(_random_value(rng))
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


def _framed(texts: list[str]) -> bytes:
    out = bytearray()
    for t in texts:
        data = t.encode("utf-8")
        out += str(len(data)).encode() + b"\n" + data
    return bytes(out)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class JsonAgainstPython(unittest.TestCase):
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

    def check(self, implementations: dict[str, list[str]], texts: list[str], compare_errors: bool) -> int:
        cases = [(t, e) for t in texts if (e := _expected(t)) is not None]
        data = _framed([t for t, _ in cases])
        for impl, argv in implementations.items():
            with self.subTest(implementation=impl):
                proc = subprocess.run(argv, input=data, capture_output=True, timeout=600)
                self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
                lines = proc.stdout.decode("utf-8").split("\n")[:-1]
                self.assertEqual(len(lines), len(cases))
                wrong = []
                for (text, expected), got in zip(cases, lines):
                    if expected.startswith("err") and not compare_errors:
                        ok = got.startswith("err")
                    else:
                        ok = got == expected
                    if not ok:
                        wrong.append(f"{text!r}\n  python: {expected[:200]!r}\n  myla:   {got[:200]!r}")
                self.assertEqual(wrong[:5], [], f"{len(wrong)} of {len(cases)} differ")
        return len(cases)

    def test_valid_texts(self) -> None:
        n = self.check(self.native, _valid_texts(1, 1500), True)
        self.assertGreater(n, 2900)

    def test_broken_texts(self) -> None:
        n = self.check(self.native, _broken_texts(2, 3000), sys.version_info >= (3, 13))
        self.assertGreater(n, 2500)

    def test_floats(self) -> None:
        rng = random.Random(3)
        floats = [_random_float(rng) for _ in range(5000)]
        texts = [_canonical(floats[i:i + 50]) for i in range(0, len(floats), 50)]
        self.check(self.native, texts, True)

    def test_interpreters(self) -> None:
        texts = _valid_texts(4, 15, bits=False) + _broken_texts(5, 30)
        self.check(self.interpreters, texts, sys.version_info >= (3, 13))

    def test_nesting_limit(self) -> None:
        deep = "[" * 500 + "]" * 500
        too_deep = "[" * 501 + "]" * 501
        expected = ["ok " + deep, "err 1 501 Too deeply nested"]
        data = _framed([deep, too_deep])
        for impl, argv in self.native.items():
            with self.subTest(implementation=impl):
                proc = subprocess.run(argv, input=data, capture_output=True, timeout=60)
                self.assertEqual(proc.stdout.decode().split("\n")[:-1], expected)


class StdTests(unittest.TestCase):
    def test_the_modules_own_tests_pass(self) -> None:
        for name in ("num", "json"):
            with self.subTest(module=name):
                path = os.path.join(_REPO, "src", "myla", "std", name + ".my")
                proc = subprocess.run([sys.executable, os.path.join(_REPO, "myla.py"), "test", path],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
